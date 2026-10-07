# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   OpenBench is a chess engine testing framework by Andrew Grant.          #
#   <https://github.com/AndyGrant/OpenBench>  <andrew@grantnet.us>          #
#                                                                           #
#   OpenBench is free software: you can redistribute it and/or modify       #
#   it under the terms of the GNU General Public License as published by    #
#   the Free Software Foundation, either version 3 of the License, or       #
#   (at your option) any later version.                                     #
#                                                                           #
#   OpenBench is distributed in the hope that it will be useful,            #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of          #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           #
#   GNU General Public License for more details.                            #
#                                                                           #
#   You should have received a copy of the GNU General Public License       #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.   #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import argparse
import hashlib
import os
import platform
import requests
import shutil
import subprocess
import tempfile
import zipfile

## Local imports must only use "import x", never "from x import ..."

IS_WINDOWS = platform.system() == 'Windows' # Don't touch this
IS_LINUX   = platform.system() != 'Windows' # Don't touch this


class OpenBenchFatalWorkerException(Exception):
    def __init__(self, message):
        self.message = 'Restarting Worker: ' + message
        super().__init__(self.message)

class OpenBenchBuildFailedException(Exception):
    def __init__(self, message, logs):
        self.message = message
        self.logs    = logs
        super().__init__(self.message)

class OpenBenchBadBenchException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class OpenBenchCorruptedNetworkException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class OpenBenchCorruptedBookException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class OpenBenchMissingAPICredentialsException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class OpenBenchBadServerResponseException(Exception):
    def __init__(self):
        self.message = ''
        super().__init__(self.message)

class OpenBenchFailedGenfensException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class OpenBenchMatchRunnerFailedException(Exception):
    def __init__(self, message, logs):
        self.message = message
        self.logs    = logs
        super().__init__(self.message)


def kill_process_by_name(process_name):

    process_name = os.path.basename(process_name)

    # Usually the process has already exited, so hide the complaints about not finding it
    quiet = { 'stdout' : subprocess.DEVNULL, 'stderr' : subprocess.DEVNULL }

    if IS_LINUX:
        subprocess.run(['pkill', '-KILL', '-f', process_name], **quiet)

    if IS_WINDOWS:
        subprocess.run(['taskkill', '/f', '/im', process_name], **quiet)

def url_join(*args, trailing_slash=True):

    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + ['', '/'][trailing_slash]

def credentialed_cmdline_args(parser=None):

    # Adds username, password, and server to the ArgumentParser
    # Defers to the env variables for them, if not provided explicitly

    # Don't require inheritence from an existing ArgumentParser
    if not parser:
        parser = argparse.ArgumentParser()

    # We can use ENV variables for Username, Password, and Server
    req_user   = 'OPENBENCH_USERNAME' not in os.environ
    req_pass   = 'OPENBENCH_PASSWORD' not in os.environ
    req_server = 'OPENBENCH_SERVER'   not in os.environ

    # For clarity, seperate out this help text
    help_user   = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass   = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'
    help_server = '  Server. May also be passed as OPENBENCH_SERVER   environment variable'

    # Parse all arguments, all of which must exist in some form
    parser.add_argument('-U', '--username', help=help_user    , required=req_user  )
    parser.add_argument('-P', '--password', help=help_pass    , required=req_pass  )
    parser.add_argument('-S', '--server'  , help=help_server  , required=req_server)
    args = parser.parse_args()

    # Fallback on ENV variables for Username, Password, and Server
    args.username = args.username if args.username else os.environ['OPENBENCH_USERNAME']
    args.password = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
    args.server   = args.server   if args.server   else os.environ['OPENBENCH_SERVER'  ]

    return args

def credentialed_request(server, username, password, endpoint):

    target  = url_join(server, *endpoint.split('/'))
    payload = { 'username' : username, 'password' : password }

    return requests.post(data=payload, url=target)

def read_git_credentials(engine):
    fname = 'credentials.%s' % (engine.replace(' ', '').lower())
    if os.path.exists(fname):
        with open(fname) as fin:
            return { 'Authorization' : 'token %s' % fin.readlines()[0].rstrip() }
    raise OpenBenchMissingAPICredentialsException('%s not found' % fname)


def engine_binary_name(engine, commit_sha, net_path):
    name = '%s-%s' % (engine, commit_sha.upper()[:8])
    if net_path:
        name += '-%s' % (net_path[-8:])
    return name

def check_for_engine_binary(out_path):

    # The point of this is to deal with a lacking .exe
    assert not out_path.endswith('.exe')

    # Check for already having the binary ( Linux )
    if IS_LINUX and os.path.isfile(out_path):
        return out_path

    # Check for already having the binary ( Windows )
    if IS_WINDOWS and os.path.isfile('%s.exe' % (out_path)):
        return '%s.exe' % (out_path)

    # Sanity check to force Windows to have .exe extensions
    if IS_WINDOWS and os.path.isfile(out_path):
        os.rename(out_path, '%s.exe' % (out_path))
        return '%s.exe' % (out_path)

def makefile_command(net_path, make_path, out_path, compiler, jobs=None):

    # Build with a bounded -j, as an unbounded one starts every compile at once,
    # which can exhaust the memory of small machines. EXE= controls the output location
    command = ['make', '-j%d' % (jobs or os.cpu_count() or 1), 'EXE=%s' % (out_path)]

    # Build with CC/CXX= when using a custom compiler
    if compiler and not any(rc in compiler for rc in ('rustc','cargo')):
        comp_flag = ['CC', 'CXX']['++' in compiler]
        command  += ['%s=%s' % (comp_flag, compiler)]

    # Build with EVALFILE= to embed NNUE files
    if net_path:
        command += ['EVALFILE=%s' % (os.path.abspath(net_path).replace('\\', '/'))]

    return command


def download_opening_book(server, book_sha, book_source, book_name):

    book_path = os.path.join('Books', book_name)

    # Datagen workloads might not include a book
    if book_name.upper() == 'NONE':
        return

    # Book might already have been downloaded
    if not os.path.exists(book_path):

        print ('Fetching Opening Book [%s]' % (book_name))

        # Sources are either absolute (Github), or served by the OpenBench server
        if not book_source.startswith(('https://', 'http://')):
            book_source = url_join(server, book_source)

        response = requests.get(book_source)
        if response.status_code != 200:
            raise OpenBenchCorruptedBookException(
                'Unable to fetch %s (HTTP %d)' % (book_name, response.status_code))

        # Work with temp files and directories until finished extracting
        with tempfile.TemporaryDirectory() as temp_dir:

            download_path = os.path.join(temp_dir, book_name)
            with open(download_path, 'wb') as fout:
                fout.write(response.content)

            # Github hosted books are .zip files, containing only the book
            if zipfile.is_zipfile(download_path):
                unzip_path = os.path.join(temp_dir, 'unzipped')
                with zipfile.ZipFile(download_path, 'r') as zip_file:
                    zip_file.extractall(unzip_path)
                download_path = os.path.join(unzip_path, os.listdir(unzip_path)[0])

            shutil.move(download_path, book_path)

    # Verify SHAs match with the server. Read as bytes, so that line endings
    # are never translated, and the sha is the same on every platform
    with open(book_path, 'rb') as fin:
        sha256 = hashlib.sha256(fin.read()).hexdigest()

    # Log SHAs on every workload
    print ('Correct  %s' % (book_sha.upper()))
    print ('Download %s\n' % (sha256.upper()))

    # We have to have the correct SHA to continue
    if book_sha.upper() != sha256.upper():
        os.remove(book_path)
        raise OpenBenchCorruptedBookException('Invalid sha for %s' % (book_name))

def download_network(server, username, password, engine, net_name, net_sha, net_path):

    # Avoid redownloading Network files
    if not os.path.isfile(net_path):

        # Format the API request, including credentials
        print ('Fetching %s (%s) for %s' % (net_name, net_sha, engine))
        endpoint = 'api/networks/%s/%s' % (engine, net_sha)
        request  = credentialed_request(server, username, password, endpoint)

        # Write the content out to the net_path in kb chunks
        with open(net_path, 'wb') as fout:
            for chunk in request.iter_content(chunk_size=1024):
                if chunk: fout.write(chunk)
            fout.flush()

    else:
        print ('Found %s (%s) for %s' % (net_name, net_sha, engine))

    # Check for the first 8 characters of the sha256
    print ('Verifying %s (%s) for %s\n' % (net_name, net_sha, engine))
    with open(net_path, 'rb') as network:
        sha256 = hashlib.sha256(network.read()).hexdigest()[:8]

    # Verify the download and delete partial or corrupted ones
    if net_sha.upper() != sha256.upper():
        os.remove(net_path)
        raise OpenBenchCorruptedNetworkException('Invalid SHA for %s' % (net_name))

def prepare_engine(engine, net_path, branch, source, make_path, out_path, private, compiler=None, jobs=None):

    # Check to see if we already have the binary
    if check_for_engine_binary(out_path):
        print('Found [%s-%s]' % (engine, branch))
        return os.path.basename(check_for_engine_binary(out_path))

    # Private engines require credentialed headers to fetch the source
    headers = read_git_credentials(engine) if private else None

    # Work with temp files and directories until finished building
    with tempfile.TemporaryDirectory() as temp_dir:

        print('Building [%s-%s]' % (engine, branch))

        # Download the zip file from Github. Errors, such as a bad token in the
        # credentials file, come back as a JSON message instead of a .zip
        response = requests.get(source, headers=headers)
        if response.status_code != 200:
            try: reason = response.json().get('message', '')
            except ValueError: reason = ''
            raise Exception('Unable to download [%s-%s] from Github: HTTP %d %s%s' % (
                engine, branch, response.status_code, reason,
                '. Check credentials.%s' % (engine.replace(' ', '').lower()) if private else ''))

        zip_path = os.path.join(temp_dir, '%s-tmp' % (engine))
        with open(zip_path, 'wb') as zip_file:
            zip_file.write(response.content)

        # Unzip the engine to a directory called <engine>
        unzip_path = os.path.join(temp_dir, engine)
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            zip_file.extractall(unzip_path)

        # Rename the Root folder for ease of conventions
        unzip_root = os.path.join(unzip_path, os.listdir(unzip_path)[0])
        src_path   = os.path.join(unzip_path, '%s-tmp' % (engine))
        os.rename(unzip_root, src_path)

        # Prepare the MAKEFILE command
        make_path = os.path.join(src_path, make_path)
        bin_path  = os.path.join(make_path, os.path.basename(out_path))
        make_cmd  = makefile_command(net_path, make_path, os.path.basename(out_path), compiler, jobs)

        # Build the engine, which will produce a binary to bin_path, to be moved after
        process     = subprocess.Popen(make_cmd, cwd=make_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        comp_output = process.communicate()[0].decode('utf-8')

        # Verify that the compilation subprocess did not exit with errors
        if process.returncode:
            message = 'Error during compilation. The logs have been sent to the server'
            raise OpenBenchBuildFailedException(message, comp_output)

        # Move the binary to the proper out_path, account for Windows and cross-drive moves
        if check_for_engine_binary(bin_path):
            shutil.move(check_for_engine_binary(bin_path), os.path.dirname(out_path))

    # Check to see if we have the binary
    if check_for_engine_binary(out_path):
        return os.path.basename(check_for_engine_binary(out_path))

    # Someone should catch this, and possibly report it to the OpenBench server
    message = 'Error during compilation. The logs have been sent to the server'
    raise OpenBenchBuildFailedException(message, comp_output)
