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

# Prepares the training data of 4PC Datagen Workloads for the trainer.
#
# Workers keep their data in Client/Datagen/<test>/, as NNUEDAT2 files that are
# usually compressed with xz. Given those files, or the folders holding them, this
# unpacks them into <out>/train/ and <out>/validation/. A position that is in more
# than one file, with the same pieces and side to move, is only kept once. The
# engine already skips repeated positions within a Workload, so this only finds
# those repeated between Workloads, and no position is in both of the splits.
#
#   python Scripts/datagen_collect.py Datagen/ --out data --validation 1000000
#
# Requires numpy.

import argparse
import lzma
import struct
import sys

from pathlib import Path

import numpy as np

# NNUEDAT2, as written by the engine's tools/sfen_stream.h
HEADER      = struct.Struct('<8sQQQ')
RECORD_SIZE = 188
BIN_MAGIC   = b'NNUEDAT2'
BIN_SCHEMA  = 0x4650434654303031

# The pieces and side to move, and the game id, of each record
POSITION_SIZE, GAME_OFFSET = 161, 172

def fnv1a(data):

    # The checksum of the records, as in the engine. Only needed for rewritten files
    h = 14695981039346656037
    for byte in data:
        h = ((h ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h

def read_file(path):

    opener = lzma.open if path.suffix == '.xz' else open
    with opener(path, 'rb') as fin:
        raw = fin.read()

    magic, count, schema, checksum = HEADER.unpack_from(raw)
    if magic != BIN_MAGIC or schema != BIN_SCHEMA or len(raw) != HEADER.size + count * RECORD_SIZE:
        raise ValueError('%s is not a complete NNUEDAT2 file' % (path))

    return raw

def position_keys(raw):

    # 64 bit hashes of the pieces and side to move of every record
    count   = (len(raw) - HEADER.size) // RECORD_SIZE
    records = np.frombuffer(raw, dtype=np.uint8, offset=HEADER.size).reshape(count, RECORD_SIZE)

    padded = np.zeros((count, 168), dtype=np.uint8)
    padded[:, :POSITION_SIZE] = records[:, :POSITION_SIZE]

    keys = np.full(count, 0xCBF29CE484222325, dtype=np.uint64)
    with np.errstate(over='ignore'):
        for word in padded.view('<u8').T:
            keys = (keys ^ word) * np.uint64(0x100000001B3)
            keys ^= keys >> np.uint64(29)

    return keys

def game_ids(raw):

    # Records are 188 bytes, so the 8 bytes of each id are taken out before reading them
    records = np.frombuffer(raw, dtype=np.uint8, offset=HEADER.size).reshape(-1, RECORD_SIZE)
    return records[:, GAME_OFFSET:GAME_OFFSET + 8].copy().view('<u8').ravel()

def find_inputs(paths):

    files = []
    for path in map(Path, paths):
        if path.is_dir():
            files += [p for p in path.rglob('*') if p.name.endswith(('.bin', '.bin.xz'))]
        else:
            files.append(path)

    # The same Workload's data once, even if collected twice or both compressed and not
    unique = {}
    for path in sorted(files):
        unique.setdefault(path.name.removesuffix('.xz'), path)

    return [unique[name] for name in sorted(unique)]

def main():

    p = argparse.ArgumentParser(description='Prepares the training data of 4PC Datagen Workloads')
    p.add_argument('inputs'      , help='NNUEDAT2 files, or folders holding them', nargs='+'          )
    p.add_argument('--out'       , help='Folder for train/ and validation/'      , required=True      )
    p.add_argument('--validation', help='Positions for validation, from whole files', type=int, default=0)
    args = p.parse_args()

    inputs = find_inputs(args.inputs)
    if not inputs:
        sys.exit('No .bin or .bin.xz files were found')

    train, validation = Path(args.out) / 'train', Path(args.out) / 'validation'
    train.mkdir(parents=True, exist_ok=True)
    validation.mkdir(parents=True, exist_ok=True)

    # The trainer rejects files without positions, so they are left out
    inputs = [path for path in inputs if len(read_file(path)) > HEADER.size]

    # First pass: unpack every file, and hash its positions
    outputs, keys, games = [], [], []
    for index, path in enumerate(inputs):
        raw    = read_file(path)
        output = train / path.name.removesuffix('.xz')
        output.write_bytes(raw)
        outputs.append(output)
        keys.append(position_keys(raw))
        games.append(np.unique(game_ids(raw)))
        print('[%d/%d] %s: %d positions' % (index + 1, len(inputs), path, len(keys[-1])), flush=True)

    # Keep the first of every position, so files are only rewritten when they lose one
    every    = np.concatenate(keys)
    starts   = np.cumsum([0] + [len(k) for k in keys])
    _, first = np.unique(every, return_index=True)
    keep     = np.zeros(len(every), dtype=bool)
    keep[first] = True
    masks    = [keep[starts[i]:starts[i + 1]] for i in range(len(inputs))]

    # Whole files from the end go to validation, until it holds enough positions
    total = 0
    for index in reversed(range(len(inputs))):
        if total >= args.validation:
            break
        if masks[index].any():
            outputs[index] = outputs[index].replace(validation / outputs[index].name)
            total += int(masks[index].sum())

    # Second pass: rewrite the files that lost positions, and drop any left empty
    for output, mask in zip(outputs, masks):
        if mask.all():
            continue

        raw     = output.read_bytes()
        records = np.frombuffer(raw, dtype=np.uint8, offset=HEADER.size).reshape(-1, RECORD_SIZE)[mask]
        if not len(records):
            output.unlink()
            continue

        data = records.tobytes()
        output.write_bytes(HEADER.pack(BIN_MAGIC, len(records), BIN_SCHEMA, fnv1a(data)) + data)

    totals = { name : sum(int(m.sum()) for o, m in zip(outputs, masks) if o.parent == folder)
               for name, folder in (('train', train), ('validation', validation)) }

    # Different Workloads have different seeds, so a game id in two files means repeated data
    all_games = np.concatenate(games)
    repeated  = len(all_games) - len(np.unique(all_games))

    print('\nFiles      : %d' % (len(inputs)))
    print('Positions  : %d, of which %d were repeats' % (len(every), len(every) - len(first)))
    print('Train      : %d positions in %s' % (totals['train'], Path(args.out) / 'train'))
    print('Validation : %d positions in %s' % (totals['validation'], Path(args.out) / 'validation'))
    print('Games      : %d, with %d game ids in more than one file' % (len(all_games), repeated))

if __name__ == '__main__':
    main()
