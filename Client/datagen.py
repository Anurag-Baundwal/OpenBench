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

# The main purpose of this module is to invoke run_datagen(). Refer to
# complete_datagen_workload() in Client/worker.py for how it is used.
#
# 4PC Datagen Workloads do not play games with the match runner. Instead, the
# engine runs its own generate_training_data command, the training data generator
# of Stockfish's tools branch, with one game per thread. The engine is given
# commands like the following on its standard input:
#
#   setoption name Threads value 8
#   setoption name Hash value 128
#   generate_training_data depth 30 nodes 5000 <extra> book Books/openbench.datagen.epd
#       count 204800 seed S output_file_name Datagen/<test>/<test>.<result>.<book index>
#   quit
#
# The data stays on the Worker, in Datagen/<test>/, as NNUEDAT2 files compressed
# with xz. They are collected by hand, and checked with Scripts/datagen_collect.py.
#
# run_datagen() may raise utils.OpenBenchFailedDatagenException, when the engine
# exits without finishing. The data it wrote until then remains usable.

import collections
import lzma
import os
import re
import shutil
import struct
import subprocess
import threading
import time

## Local imports must only use "import x", never "from x import ..."

import utils

# NNUEDAT2, as written by the engine's tools/sfen_stream.h. A 32 byte header,
# holding the number of records, then the records of 188 bytes each
HEADER      = struct.Struct('<8sQQQ')
RECORD_SIZE = 188
BIN_MAGIC   = b'NNUEDAT2'
BIN_SCHEMA  = 0x4650434654303031

# Offsets in a record of the side to move, its team's result, and the game's id
SIDE_OFFSET, RESULT_OFFSET, GAME_OFFSET = 160, 161, 172

# A game of the default settings writes about 100 positions
POSITIONS_PER_GAME = 100

FINISHED_LINE = 'INFO: generate_training_data finished.'

def datagen_games(config):

    runner_cnt = config.workload['distribution']['runner-count']
    rounds_per = config.workload['distribution']['rounds-per-runner']

    return runner_cnt * rounds_per

def datagen_threads(config):

    runner_cnt      = config.workload['distribution']['runner-count']
    concurrency_per = config.workload['distribution']['concurrency-per']

    return runner_cnt * concurrency_per

def datagen_book(config):

    # The engine only reads books with an .epd extension
    book_name = config.workload['test']['book']['name']
    if book_name.upper() == 'NONE':
        return None

    book_path = os.path.join('Books', 'openbench.datagen.epd')
    shutil.copyfile(os.path.join('Books', book_name), book_path)

    return book_path

def datagen_output_name(config):

    test_id    = config.workload['test']['id']
    result_id  = config.workload['result']['id']
    book_index = config.workload['test']['book_index']

    folder = os.path.join('Datagen', str(test_id))
    os.makedirs(folder, exist_ok=True)

    return os.path.join(folder, '%d.%d.%d' % (test_id, result_id, book_index))

def datagen_seed(config):

    # The Server gives every Workload of a Test a new book index
    return config.workload['test']['id'] * 2**32 + config.workload['test']['book_index']

def datagen_limits(config):

    # The Server only creates Datagen Workloads with nodes or depth limits
    time_control = config.workload['test']['dev']['time_control'].upper()

    if (match := re.fullmatch(r'N=(\d+)', time_control)):
        return 'depth 30 nodes %s' % (match.group(1))

    if (match := re.fullmatch(r'D=(\d+)', time_control)):
        return 'depth %s' % (match.group(1))

    raise utils.OpenBenchFatalWorkerException('Datagen requires N= or D=, not %s' % (time_control))

def datagen_commands(config, book_path, output_name):

    threads = datagen_threads(config)
    options = config.workload['test']['dev']['options']

    # Options are per game, and every thread plays one game at a time
    commands = []
    for name, value in re.findall(r'(\S+?)=("[^"]*"|\'[^\']*\'|\S*)', options):
        value = value.strip('"\'')
        if name == 'Threads':
            commands.insert(0, 'setoption name Threads value %d' % (threads))
        elif name == 'Hash':
            commands.append('setoption name Hash value %d' % (int(value) * threads))
        else:
            commands.append('setoption name %s value %s' % (name, value))

    # The Workload's own settings come last, so that the extra arguments cannot change them
    arguments = [datagen_limits(config), config.workload['test']['genfens_args']]
    if book_path:
        arguments.append('book %s' % (book_path))
    arguments.append('count %d' % (datagen_games(config) * POSITIONS_PER_GAME))
    arguments.append('seed %d' % (datagen_seed(config)))
    arguments.append('output_file_name %s' % (output_name))

    commands.append(' '.join(['generate_training_data'] + [x for x in arguments if x]))
    commands.append('quit')

    return commands

def datagen_positions(path):

    # The header is rewritten after every write, so the file is always complete
    try: return max(0, os.path.getsize(path) - HEADER.size) // RECORD_SIZE
    except OSError: return 0

def run_datagen(engine, commands, data_path, heartbeat, report_interval):

    # Returns once the engine finished, or after stopping it when heartbeat()
    # returns True or openbench.exit is created. The engine is never left running

    binary  = os.path.join('Engines', engine)
    process = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output  = collections.deque(maxlen=100)

    def read_output():
        for line in iter(process.stdout.readline, b''):
            output.append(line.decode('utf-8', errors='replace').rstrip())

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    try:
        process.stdin.write(('\n'.join(commands) + '\n').encode())
        process.stdin.flush()

        last_report = time.time()
        while process.poll() is None:

            time.sleep(1)

            # Report progress to the Server, which may say that the Test ended
            if time.time() - last_report >= report_interval:
                last_report = time.time()
                print('Datagen: %d positions written' % (datagen_positions(data_path)))
                if heartbeat():
                    return print('The Test has finished, stopping the engine')

            if os.path.isfile('openbench.exit'):
                return print('Stopping the engine, as openbench.exit was found')

    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=5)

    # A finished engine has printed the final line, and exited normally. Progress
    # dots are printed without newlines, so the line may start with some of them
    if process.returncode != 0 or not any(FINISHED_LINE in line for line in output):
        message = 'generate_training_data failed, exit code %d' % (process.returncode)
        raise utils.OpenBenchFailedDatagenException(message, '\n'.join(output))

def read_datagen_results(path):

    # Returns the positions in an NNUEDAT2 file, and the [L, D, W] of its games for
    # Red and Yellow. Each record holds the result for the team of the side to move

    if not os.path.isfile(path):
        return 0, [0, 0, 0]

    with open(path, 'rb') as fin:
        magic, count, schema, checksum = HEADER.unpack(fin.read(HEADER.size))
        data = fin.read()

    if magic != BIN_MAGIC or schema != BIN_SCHEMA or len(data) != count * RECORD_SIZE:
        raise utils.OpenBenchFailedDatagenException('%s is not a complete NNUEDAT2 file' % (path), '')

    results = {}
    for offset in range(0, len(data), RECORD_SIZE):
        game = struct.unpack_from('<Q', data, offset + GAME_OFFSET)[0]
        if game not in results:
            result = struct.unpack_from('<b', data, offset + RESULT_OFFSET)[0]
            results[game] = result if data[offset + SIDE_OFFSET] % 2 == 0 else -result

    trinomial = [0, 0, 0]
    for result in results.values():
        trinomial[result + 1] += 1

    return count, trinomial

def compress_datagen_file(path):

    # xz stores NNUEDAT2 in about a tenth of its size. Written to a temporary
    # file first, so that an interruption cannot leave a broken archive behind
    if not os.path.isfile(path):
        return

    # The engine buffers 5000 positions per thread, so an early stop may leave
    # nothing but the header. The trainer rejects such files
    if datagen_positions(path) == 0:
        return os.remove(path)

    with open(path, 'rb') as fin, lzma.open(path + '.xz.tmp', 'wb') as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)

    os.replace(path + '.xz.tmp', path + '.xz')
    os.remove(path)
