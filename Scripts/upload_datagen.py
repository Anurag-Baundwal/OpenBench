#!/bin/python3

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

# Uploads the training data of a 4PC Datagen Workload to Hugging Face.
#
# Workers keep their data in Client/Datagen/<test>/. This uploads the .bin.xz
# files there that the dataset does not have yet, flat in its root, in a single
# commit. Running it again later only uploads what is new. Plain .bin files are
# left out, as they may belong to a Workload that is still running.
#
#   python Scripts/upload_datagen.py 11
#
# --dataset picks another dataset than the default one, given as its address,
# as owner/name, or as a name alone for one of the 4pc-engine organization.
# Without write access to it, --pr opens a pull request instead.
# Requires huggingface_hub, and a login with: hf auth login

import argparse
import os
import re
import sys

from pathlib import Path

try:
    from huggingface_hub import HfApi, get_token
    from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
except ImportError:
    sys.exit('huggingface_hub is not installed. Install it with:\n'
             '  %s -m pip install huggingface_hub' % Path(sys.executable).stem)

ORG     = '4pc-engine'
DATASET = ORG + '/stockfish-4pc-nnue-training-data'

def dataset_id(name):

    # https://huggingface.co/datasets/<owner>/<name>, perhaps with /tree/main after it
    match = re.match(r'(?:https?://)?(?:www\.)?huggingface\.co/datasets/([^/]+/[^/?#]+)', name)
    if match:
        return match.group(1)
    if re.fullmatch(r'[\w.-]+/[\w.-]+', name):
        return name
    # A name alone is one of the datasets of the project's organization
    if re.fullmatch(r'[\w.-]+', name):
        return ORG + '/' + name
    sys.exit('Not a dataset: %s. Give its address, owner/name, or a name in %s' % (name, ORG))

def upload_datagen():

    p = argparse.ArgumentParser()
    p.add_argument('test', help='Test id, as in Client/Datagen/<test>, or a folder holding its files')
    p.add_argument('--dataset', help='Dataset address or owner/name (default %s)' % DATASET, default=DATASET)
    p.add_argument('--pr', help='Open a pull request instead of committing to main', action='store_true')
    args = p.parse_args()
    dataset = dataset_id(args.dataset)

    folder = Path(args.test)
    if not folder.is_dir():
        folder = Path(__file__).resolve().parent.parent / 'Client' / 'Datagen' / args.test
    if not folder.is_dir():
        sys.exit('Found no folder %s' % folder)

    if not get_token():
        sys.exit('Not logged in to Hugging Face. Log in with:\n  hf auth login')

    api = HfApi()
    try:
        uploaded = set(api.list_repo_files(dataset, repo_type='dataset'))
    except RepositoryNotFoundError:
        sys.exit('Found no dataset %s, or this account cannot see it' % dataset)
    files    = sorted(f.name for f in folder.iterdir() if f.name.endswith('.bin.xz'))
    new      = [f for f in files if f not in uploaded]
    unpacked = [f.name for f in folder.iterdir() if f.name.endswith('.bin')]

    size = sum((folder / f).stat().st_size for f in new)
    print('%s: %d files, %d new (%.1f MB) for %s' % (folder, len(files), len(new), size / 1e6, dataset))
    for f in new:
        print('  ' + f)

    if unpacked:
        print('Leaving out %d .bin files, of Workloads that are running or were stopped' % len(unpacked))

    if not new:
        return

    # The file names begin with the test id, as in <test>.<result>.<n>.bin.xz
    tests   = sorted({f.split('.')[0] for f in new}, key=lambda t: (len(t), t))
    message = 'Upload %d file%s of test%s %s' % (
        len(new), '' if len(new) == 1 else 's', '' if len(tests) == 1 else 's', ', '.join(tests))

    try:
        commit = api.upload_folder(
            repo_id=dataset, repo_type='dataset', folder_path=folder,
            allow_patterns=new, commit_message=message, create_pr=args.pr)
    except HfHubHTTPError as error:
        if error.response.status_code == 403 and not args.pr:
            sys.exit('No write access to %s. Run again with --pr to open a pull request' % dataset)
        raise

    print(commit.pr_url if args.pr else commit.commit_url)

if __name__ == '__main__':
    upload_datagen()
