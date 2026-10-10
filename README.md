# OpenBench for 4PC Teams

A fork of [OpenBench](https://github.com/AndyGrant/OpenBench) for testing four-player teams chess engines, such as stockfish_4pc. You create a test on the website, comparing two commits of the engine. Anyone with a registered account runs the Client on their machine, and their machines play games for it. The server combines the results into a single SPRT, or a fixed number of games.

## How it works

- The **server** is a Django website. It stores tests, assigns work, and computes the SPRT. It needs no CPU power, so a small host such as PythonAnywhere is enough.
- Each **worker** runs `Client/client.py`. For every workload it downloads both engine commits from GitHub and builds them with `make`. It checks each build's `bench`, then plays games with `match.py`, the 4pc_arena match runner, which ships with the Client.
- Openings come from `Books/fens_100k.txt`, 100,000 balanced 4PC FENs, which the server hosts itself. Every pair of games shares an opening, with the engines swapping teams, and every workload uses new openings.
- `Scripts/generate_fens.py` made the book: 8 plies from the start position, each picked among the moves within 100 cp of the best, kept only if both the NNUE and the hand crafted evaluation builds of stockfish_4pc find the result within 100 cp. The older `Books/fens.txt`, 10,000 positions from 4 random plies, stays for the tests that were created with it.
- Results are pentanomial pairs, and the SPRT uses normalized Elo, the same model as `match.py --sprt`.

## Running the server

```
pip install -r requirements.txt
python manage.py migrate
python manage.py import_engines Engines/stockfish_4pc.json
python manage.py runserver 0.0.0.0:8000
```

- **Account:** register on the website, then enable your account as an approver:
  `python manage.py shell -c "from OpenBench.models import Profile; Profile.objects.filter(user__username='NAME').update(enabled=True, approver=True, superuser=True)"`.
  Enable other people's accounts from Django's admin at `/admin/`, after creating an admin login with `python manage.py createsuperuser`.
- **Private engine:** stockfish_4pc is a private repository, so the server needs a GitHub token that can read it, saved as `Config/credentials.stockfish_4pc`. Use a fine-grained token with Contents: Read-only on that one repository.
- **Engine settings:** edit these at `/manage/engines/`. Set `nps` to the "Speed for ..." line your reference machine prints with its usual `-T`. Time controls then play unscaled there, and proportionally longer on slower machines.
- **Public deployments:** set the environment variables `OPENBENCH_SECRET_KEY` (your own random secret) and `OPENBENCH_DEBUG=false`, and serve `/static/` from `OpenBench/static/`.
- **No threads:** uploaded PGNs are archived by a background thread. Hosts that don't allow threads in web apps, such as PythonAnywhere, never archive them, so leave Upload PGNs off there.

## Running a test

Open **Create Test** and choose the Dev and Base branches, or full commit SHAs. The engine presets fill in the rest:

- **Bench:** the node count of `./stockfish_4pc bench` for each commit. Either type it in, or end the commit message with `Bench: 1234567`, and OpenBench reads it from there.
- **Time control:** `base+inc` in seconds, e.g. `10.0+0.1` is match.py's `--tc 10000 --inc 100`. `N=` nodes, `D=` depth and `MT=` movetime in milliseconds also work. Dev and Base must use the same time control, and cyclic (`40/...`) time controls are rejected.
- **SPRT bounds:** normalized Elo, e.g. `[0.00, 3.00]`.

## Generating training data

Open **Create Datagen**. The engine preset fills in the measured settings:
- the branch `tools/datagen-nnuedat2`, which has the engine's `generate_training_data`;
- `N=5000` and `Threads=1 Hash=16`;
- the opening randomization, in **Datagen Args**.

The time control must be `N=` or `D=`.

- **What a workload does:** it runs the engine's own `generate_training_data`, the training data generator of Stockfish's tools branch, with one game per thread and a seed of its own.
- **When it ends:** workers report the games they finished, and the test ends at **Max Games**. A game writes about 100 positions, so 1,400,000 games is about 140M positions.
- **Where the data goes:** it stays on each worker, in `Client/Datagen/<test id>/`, as NNUEDAT2 files compressed with xz, at about 10.5 bytes per position. Nothing is uploaded, since the server couldn't store it.
- **Collecting it:** copy the `Datagen/` folders from every machine, then run `python Scripts/datagen_collect.py <folders...> --out data --validation 1000000` (it needs numpy). It:
  - unpacks the files into `data/train/` and `data/validation/`, for the trainer;
  - keeps each position only once;
  - never puts a position in both folders.
- **Datagen Args:** extra options of `generate_training_data`. The worker sets the book, count, seed and output file itself.

## Contributing a machine

Each worker needs:

- Python 3.9+ with `pip install -r Client/requirements.txt`, ideally in a venv (the top-level `requirements.txt` is only for the server)
- `make` and a C++ compiler (`g++` or `clang++`)
- a GitHub token that can read stockfish_4pc, saved as `Client/credentials.stockfish_4pc`
- an enabled account on the server

Then, from `Client/`:

```
python client.py -U NAME -P "PASSWORD" -S https://SERVER -T 8 -I MACHINE_NAME
```

`-T` is the number of games played at once. Leave a core or two free for the system. `-I` optionally names the machine on the `/machines/` page. `-N`, the number of CPU sockets, defaults to 1.

- **Windows:** install [MSYS2](https://www.msys2.org/), then run `pacman -S --needed mingw-w64-ucrt-x86_64-gcc make` once in its UCRT64 terminal. Run the worker itself from a normal Command Prompt with your Windows Python. It finds MSYS2 in `C:\msys64` by itself (set `MSYS2_ROOT` if it's elsewhere) and puts its compilers first on its own `PATH`, since DLLs from other programs can otherwise make `g++` fail silently.
- **Termux:** `pkg install python clang make`, then `pip install -r Client/requirements.txt`. Run `termux-wake-lock` first, or Android may pause the worker.

Every machine must produce the same `bench` node count for a given commit, since a mismatch stops the test. Check this once on each new kind of machine, e.g. ARM vs x86, before relying on it.

To stop a worker cleanly, create a file named `openbench.exit` in `Client/`.

## Differences from upstream OpenBench

- `match.py` replaces fastchess, so there is nothing to download or build for the match runner.
- The standard chess books are disabled in favor of `fens_100k.txt` and `fens.txt`.
- Datagen runs the engine's own `generate_training_data`, rather than genfens openings and games, and the data stays on the workers rather than being uploaded as PGNs.
- Syzygy and win/draw adjudication are not supported. `match.py` itself draws games by threefold repetition, the fifty-move rule (200 plies) and its 1000-ply limit. Checkmate, stalemate and king captures are taken from the engines, which report when they have no legal move.

## Updating match.py

`Client/match.py` began as a copy of `match.py` from [the 4pc_arena fork](https://github.com/Anurag-Baundwal/4pc_arena/tree/cluster-runner), but is now maintained here, so change it in place. After changing anything in `Client/`, bump `client_version` in `Config/config.json` and `CLIENT_VERSION` in `Client/worker.py` together. Workers update themselves from `client_repo_url`, which must point at this fork.

---

## About OpenBench

OpenBench is an open-source Chess Engine Testing Framework for UCI engines. OpenBench provides a lightweight interface and client to facilitate running fixed-game tests as well as SPRT tests to benchmark changes to engines for performance and stability. OpenBench supports [Fischer Random Chess](https://en.wikipedia.org/wiki/Chess960).

OpenBench is the primary testing framework used for the development of [Ethereal.](https://github.com/AndyGrant/Ethereal) The primary instance of OpenBench can be found at [http://chess.grantnet.us](http://chess.grantnet.us/). The Primary instance of OpenBench supports development for
[Berserk](https://github.com/jhonnold/berserk), [Bit-Genie](https://github.com/Aryan1508/Bit-Genie), [BlackMarlin](https://github.com/dsekercioglu/blackmarlin), [Demolito](https://github.com/lucasart/Demolito), [Drofa](https://github.com/justNo4b/Drofa), [Ethereal](https://github.com/AndyGrant/Ethereal), [FabChess](https://github.com/fabianvdW/FabChess), [Halogen](https://github.com/KierenP/Halogen), [Igel](https://github.com/vshcherbyna/igel), [Koivisto](https://github.com/Luecx/Koivisto), [Laser](https://github.com/jeffreyan11/laser-chess-engine), [RubiChess](https://github.com/Matthies/RubiChess), [Seer](https://github.com/connormcmonigle/seer-nnue), [Stash](https://github.com/mhouppin/stash-bot), [Weiss](https://github.com/TerjeKir/weiss), [Winter](https://github.com/rosenthj/Winter), and [Zahak](https://github.com/amanjpro/zahak). A dozen or more engines are using their own private, local instances of OpenBench.

You can join OpenBench's [Discord server](https://discord.com/invite/9MVg7fBTpM) to join the discussion, see what developers are working on and talking about, or to find out how you can contribute to the project and become a part of it. OpenBench is heavily inspired by [Fishtest](https://github.com/glinscott/fishtest). The project is powered by the [Django Web Framework](https://www.djangoproject.com/) and [fastchess](https://github.com/Disservin/fastchess).

Documentation for OpenBench is available in the [Wiki](https://github.com/AndyGrant/OpenBench/wiki)
