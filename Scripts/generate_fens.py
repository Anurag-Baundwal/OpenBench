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

# Generates an opening book of balanced 4PC positions with Stockfish 4PC.
#
# Every opening starts from the standard start position. Each ply is chosen by
# a fixed depth MultiPV search, uniformly among the moves within --window of the
# best one, which is the random_multi_pv rule of Stockfish's datagen. The last
# position is searched once more, and kept if its score is within --max-score.
# A longer search then confirms it, with the stricter --confirm-score, as single
# searches of a position can disagree by more than 100 centipawns. A second
# engine, such as a build with a hand crafted evaluation, can be required to
# find the position balanced too. Positions are unique by their pieces, side
# to move and castling rights.
#
# Openings are judged in order, so a book only depends on its settings, its
# seed and the engine. An interrupted run continues where it stopped when it is
# started again with the same --out. For example:
#
#   python Scripts/generate_fens.py --engine stockfish_4pc.exe --out fens_100k.txt
#
# The defaults are for 8 plies. For 12 plies, --plies 12 --multipv 8 --window 75
# gives a similar rate of positions with a similar variety.

import argparse
import concurrent.futures
import json
import math
import os
import random
import sys
import threading
import time

from pathlib import Path

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(os.path.join(PARENT, 'Client')))

import match

# The settings that decide which positions a book holds
BOOK_SETTINGS = [
    'seed', 'plies', 'multipv', 'depth', 'window', 'abort_score',
    'max_score', 'final_nodes', 'confirm_score', 'confirm_nodes',
    'check_score', 'check_nodes',
]

# Score bands of the final positions, as used by evaluate_fens.py
SCORE_BANDS = [25, 50, 100]

# Ways an opening can be rejected
REJECTIONS = ['unbalanced', 'final', 'confirm', 'check', 'terminal', 'roundtrip', 'duplicate']


class EnginePool:

    # One engine of each kind per thread, as single threaded searches are deterministic

    def __init__(self, args):
        self.configs = { 'main' : match.EngineConfig(Path(args.engine).resolve(), { 'MultiPV' : args.multipv }, args.hash, 1) }
        if args.check_engine:
            self.configs['check'] = match.EngineConfig(Path(args.check_engine).resolve(), {}, args.hash, 1)
        self.local  = threading.local()
        self.lock   = threading.Lock()
        self.active = []
        self.names  = {}
        self.closed = False

    def get(self, kind='main'):
        engines = self.local.__dict__.setdefault('engines', {})
        if engines.get(kind) is None:
            with self.lock:
                if self.closed:
                    raise match.EngineError('The engines were closed')
                label  = '%s-%d' % (kind, len(self.active) + 1)
                engine = match.UciEngine(self.configs[kind], label=label)
                self.active.append(engine)
                self.names[kind] = engine.name
            engines[kind] = engine
        return engines[kind]

    def discard(self):
        for engine in self.local.__dict__.pop('engines', {}).values():
            engine.close(force=True)

    def close(self):
        with self.lock:
            self.closed = True
            for engine in self.active:
                engine.close(force=True)


def centipawns(result):

    # Mate scores, and searches without a score, return None
    score = result.info.get('score') if result is not None else None
    if not isinstance(score, dict) or score.get('type') != 'cp':
        return None
    return score['value']

def position_key(fen):

    # En passant squares and move counters are left out, so that a board
    # reached with and without a double pawn push is only written once
    tracker = match.PositionTracker(fen)
    return (tracker.side, tracker.castling, frozenset(tracker.board.items()))

def play_opening(pool, args, index):

    engine  = pool.get('main')
    rng     = random.Random('%d:%d' % (args.seed, index))
    moves   = []
    choices = []

    engine.new_game()
    engine.send('setoption name MultiPV value %d' % (args.multipv))

    for ply in range(args.plies):

        ranked = engine.search_multipv(moves, None, 'go depth %d' % (args.depth), args.timeout)
        scores = [centipawns(result) for result in ranked]

        # The game ended, the best move mates, or the opening is already lost
        if not ranked:
            return { 'status' : 'terminal', 'choices' : choices }
        if scores[0] is None or abs(scores[0]) > args.abort_score:
            return { 'status' : 'unbalanced', 'choices' : choices }

        candidates = [
            result.bestmove for result, score in zip(ranked, scores)
                if score is not None and score >= scores[0] - args.window
        ]

        choices.append(len(candidates))
        moves.append(rng.choice(candidates))

    engine.send('setoption name MultiPV value 1')
    final = engine.search(moves, None, 'go nodes %d' % (args.final_nodes), args.timeout)
    score = centipawns(final)

    if score is None or abs(score) > args.max_score:
        return { 'status' : 'final', 'choices' : choices }

    if args.confirm_nodes:
        final = engine.search(moves, None, 'go nodes %d' % (args.confirm_nodes), args.timeout)
        score = centipawns(final)

        if score is None or abs(score) > args.confirm_score:
            return { 'status' : 'confirm', 'choices' : choices }

    engine.set_position(moves, None)
    fen = engine.current_fen()

    # The book is read by the engine, so it must read back the same position
    engine.send('position fen %s' % (fen))
    if engine.current_fen() != fen:
        return { 'status' : 'roundtrip', 'choices' : choices }

    if args.check_engine:

        # Builds may differ in trailing commas, but must read the same position
        check = pool.get('check')
        check.new_game()
        check.send('position fen %s' % (fen))
        if check.current_fen().rstrip(',') != fen.rstrip(','):
            return { 'status' : 'roundtrip', 'choices' : choices }

        result = check.search([], fen, 'go nodes %d' % (args.check_nodes), args.timeout)
        checked = centipawns(result)

        if checked is None or abs(checked) > args.check_score:
            return { 'status' : 'check', 'choices' : choices }

    return { 'status' : 'accepted', 'choices' : choices, 'fen' : fen, 'score' : score, 'moves' : moves }

def play_opening_safely(pool, args, index):

    # A crashed or stuck engine is replaced once, and the opening tried again
    for attempt in range(2):
        try:
            return play_opening(pool, args, index)
        except (match.EngineError, TimeoutError):
            pool.discard()
            if attempt or pool.closed:
                raise


class Book:

    # The output file, and the state that lets an interrupted run continue

    def __init__(self, args):

        self.path      = Path(args.out)
        self.json_path = Path(args.out + '.json')
        self.settings  = { name : getattr(args, name) for name in BOOK_SETTINGS }

        # Whether a second engine judges the positions changes the book too
        self.settings['check_engine'] = Path(args.check_engine).name if args.check_engine else None

        if args.fresh:
            for path in (self.path, self.json_path):
                if path.exists():
                    path.unlink()

        self.state = {
            'settings'   : self.settings,
            'engine'     : None,
            'next_index' : 0,
            'stats'      : self.empty_stats(),
        }

        if self.path.exists():

            if not self.json_path.exists():
                sys.exit('%s exists without %s. Use --fresh, or another --out' % (self.path, self.json_path))

            with open(self.json_path) as fin:
                self.state = json.load(fin)

            if self.state['settings'] != self.settings:
                sys.exit('%s was made with other settings: %s. Use --fresh, or another --out' % (
                    self.path, json.dumps(self.state['settings'])))

        with open(self.path, 'a+', encoding='utf-8') as fin:
            fin.seek(0)
            fens = [line.strip() for line in fin if line.strip()]

        self.seen    = set(position_key(fen) for fen in fens)
        self.count   = len(fens)
        self.initial = len(fens)
        self.fout    = open(self.path, 'a', encoding='utf-8', newline='\n')
        self.save()

    @staticmethod
    def empty_stats():
        return {
            'openings'   : 0,
            'accepted'   : 0,
            'rejected'   : { name : 0 for name in REJECTIONS },
            'bands'      : { str(band) : 0 for band in SCORE_BANDS },
            'score_sum'  : 0,
            'log_choices': 0.0,
            'plies'      : 0,
        }

    def add(self, index, outcome):

        stats = self.state['stats']
        stats['openings'] += 1

        for count in outcome.get('choices', []):
            stats['log_choices'] += math.log(count)
            stats['plies'      ] += 1

        if outcome['status'] == 'accepted':

            key = position_key(outcome['fen'])

            if key in self.seen:
                stats['rejected']['duplicate'] += 1

            else:
                self.seen.add(key)
                self.fout.write(outcome['fen'] + '\n')
                self.fout.flush()
                self.count += 1

                stats['accepted' ] += 1
                stats['score_sum'] += outcome['score']
                for band in SCORE_BANDS:
                    if abs(outcome['score']) <= band:
                        stats['bands'][str(band)] += 1

        else:
            stats['rejected'][outcome['status']] += 1

        self.state['next_index'] = index + 1

    def save(self):
        with open(self.json_path, 'w') as fout:
            json.dump(self.state, fout, indent=4)

    def close(self):
        self.save()
        self.fout.close()


def report(book, args, started, final=False):

    stats    = book.state['stats']
    openings = max(1, stats['openings'])
    elapsed  = max(1e-9, time.time() - started)
    rate     = (book.count - book.initial) / elapsed

    print('[%6d / %d] openings %d, accepted %.1f%%, duplicates %d, %.2f positions/s%s' % (
        book.count, args.count, stats['openings'], 100.0 * stats['accepted'] / openings,
        stats['rejected']['duplicate'], rate,
        ', %.1f h left' % ((args.count - book.count) / rate / 3600) if rate and not final else ''), flush=True)

    if not final:
        return

    accepted = max(1, stats['accepted'])
    print('\nRejected  : %s' % (', '.join('%s %d' % (k, v) for k, v in stats['rejected'].items())))
    print('Scores    : %s, mean %+.1f for the side to move' % (', '.join(
        '%.1f%% within %d' % (100.0 * stats['bands'][str(band)] / accepted, band) for band in SCORE_BANDS),
        stats['score_sum'] / accepted))

    # The geometric mean of the moves to choose from, per ply
    if stats['plies']:
        branching = math.exp(stats['log_choices'] / stats['plies'])
        print('Variety   : %.2f moves to choose from per ply, about %.3g possible lines of %d plies' % (
            branching, branching ** args.plies, args.plies))
    print('Time      : %.0f s for %d positions' % (time.time() - started, book.count - book.initial))

def main():

    p = argparse.ArgumentParser(description='Generates a book of balanced 4PC openings with Stockfish 4PC')
    p.add_argument('--engine'     , help='Stockfish 4PC binary'                       , required=True       )
    p.add_argument('--out'        , help='Book to write, or to continue'              , required=True       )
    p.add_argument('--count'      , help='Positions in the finished book'             , type=int, default=100000)
    p.add_argument('--plies'      , help='Plies from the start position'              , type=int, default=8 )
    p.add_argument('--multipv'    , help='Moves searched at every ply'                , type=int, default=12)
    p.add_argument('--depth'      , help='Depth of the search at every ply'           , type=int, default=9 )
    p.add_argument('--window'     , help='Choose among moves this close to the best'  , type=int, default=100)
    p.add_argument('--abort-score', help='Abandon openings beyond this score'         , type=int, default=200)
    p.add_argument('--max-score'  , help='Keep final positions within this score'     , type=int, default=100)
    p.add_argument('--final-nodes', help='Nodes of the final search'                  , type=int, default=200000)
    p.add_argument('--confirm-score', help='Keep confirmed positions within this score', type=int, default=80)
    p.add_argument('--confirm-nodes', help='Nodes of the confirming search, 0 for none', type=int, default=500000)
    p.add_argument('--check-engine' , help='Second engine that must agree, if any'      , default=None        )
    p.add_argument('--check-score'  , help='Keep positions it finds within this score'  , type=int, default=100)
    p.add_argument('--check-nodes'  , help='Nodes of its search'                        , type=int, default=500000)
    p.add_argument('--seed'       , help='Seed of the book'                           , type=int, default=1 )
    p.add_argument('--workers'    , help='Engines searching at once'                  , type=int, default=8 )
    p.add_argument('--hash'       , help='Hash of each engine, in MB'                 , type=int, default=16)
    p.add_argument('--timeout'    , help='Seconds before a search counts as stuck'    , type=float, default=120)
    p.add_argument('--fresh'      , help='Start over, deleting --out'                 , action='store_true' )
    args = p.parse_args()

    book    = Book(args)
    pool    = EnginePool(args)
    started = time.time()
    shown   = started

    if book.count >= args.count:
        print('%s already holds %d positions' % (args.out, book.count))
        return

    print('Generating %d positions into %s, starting at opening %d' % (
        args.count - book.count, args.out, book.state['next_index']), flush=True)

    # Long runs should not pause because Windows put the computer to sleep
    if os.name == 'nt':
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
    pending  = {}
    index    = book.state['next_index']
    warned   = False

    try:
        while book.count < args.count:

            # Keep every engine busy, while judging the openings in order
            while len(pending) < 4 * args.workers:
                pending[index] = executor.submit(play_opening_safely, pool, args, index)
                index += 1

            first = min(pending)
            try:
                outcome = pending[first].result(timeout=0.5)
            except concurrent.futures.TimeoutError:
                continue

            del pending[first]
            book.add(first, outcome)

            # Openings depend on the engines, so a book should be made by the same ones
            if len(pool.names) == len(pool.configs):
                names = ', '.join(pool.names[kind] for kind in sorted(pool.names))
                if book.state['engine'] is None:
                    book.state['engine'] = names
                elif book.state['engine'] != names and not warned:
                    print('Warning: %s was started with %s' % (args.out, book.state['engine']))
                    warned = True

            if time.time() - shown >= 10:
                shown = time.time()
                book.save()
                report(book, args, started)

    except KeyboardInterrupt:
        print('\nStopped. Run the same command again to continue.')

    except match.EngineError as error:
        print('\n%s. Run the same command again to continue.' % (error))

    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        pool.close()
        book.close()

    report(book, args, started, final=True)

if __name__ == '__main__':
    main()
