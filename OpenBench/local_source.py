# Engines served from a git repository on the Server's own machine, instead of from Github.
#
# This private instance tests an engine that must not leave the owner's machines. An EngineConfig
# whose source is "local:<path to a git repo>" has its branches resolved with git, and Workers
# download each commit as a zip (`git archive`) from /clientGetSource/<engine>/<sha>/ on this Server.
# Private engines authenticate that download with the token in Config/credentials.<engine>, which
# the Workers keep in Client/credentials.<engine>, exactly as they would for Github.

import re
import subprocess

PREFIX = 'local:'

def is_local(source):
    return source.startswith(PREFIX)

def repo_path(source):
    return source[len(PREFIX):]

def git(path, *args):
    return subprocess.run(['git', '-C', path, *args], capture_output=True, check=True).stdout

def resolve(source, ref):
    """(sha, commit message) of a branch, tag or commit sha in the local repository."""
    path = repo_path(source)
    sha  = git(path, 'rev-parse', '--verify', '%s^{commit}' % (ref)).decode().strip()
    return sha, git(path, 'log', '-1', '--format=%B', sha).decode('utf-8', errors='replace')

def archive(source, sha):
    """The commit's files as a zip with one root folder, like Github's zipball."""
    assert re.fullmatch('[0-9a-f]{40}', sha)
    return git(repo_path(source), 'archive', '--format=zip', '--prefix=source/', sha)

def is_behind(source, dev_sha, base_sha):
    """True if Base has commits that Dev does not (Github's compare "ahead_by")."""
    count = git(repo_path(source), 'rev-list', '--count', '%s..%s' % (dev_sha, base_sha))
    return int(count.decode().strip()) > 0

def download_path(engine, sha):
    """Where Workers fetch the source, relative to the Server's URL."""
    return '/clientGetSource/%s/%s/' % (engine, sha)
