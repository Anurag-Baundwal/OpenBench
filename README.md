# OpenBench for 4PC Teams

This fork runs OpenBench tests for four-player teams chess engines, such as stockfish_4pc. The upstream documentation below still applies, with these differences:

- Games are played by `match.py` from the `cluster-runner` branch of [this fork of 4pc_arena](https://github.com/Anurag-Baundwal/4pc_arena/tree/cluster-runner), which ships with the Client as `Client/match.py`. It replaces fastchess, so there is nothing to download or build for the match runner.
- Openings come from `Books/fens.txt` (10,000 balanced 4PC FENs), served by the OpenBench server itself at `/api/books/fens.txt/`. The standard chess books are disabled.
- Datagen, Syzygy and win/draw adjudication are not supported. `match.py` adjudicates games itself.
- Time controls are `base+inc` in seconds (e.g. `10.0+0.1` for match.py's `--tc 10000 --inc 100`), scaled per machine by bench NPS as usual. `N=` nodes, `D=` depth and `MT=` movetime in milliseconds also work. Cyclic (`40/...`) time controls, and different time controls for Dev and Base, are rejected.
- Results are reported as pentanomial pairs, and the SPRT uses normalized Elo, the same model as `match.py --sprt`.

### Server

```
pip install -r requirements.txt
python manage.py migrate
python manage.py import_engines Engines/stockfish_4pc.json
python manage.py runserver 0.0.0.0:8000
```

stockfish_4pc is a private repository, so the server needs a GitHub token with read access to it in `Config/credentials.stockfish_4pc`. Register an account on the website, then enable it as an approver with `python manage.py shell -c "from OpenBench.models import Profile; Profile.objects.filter(user__username='NAME').update(enabled=True, approver=True, superuser=True)"`. Engine settings can be edited at `/manage/engines/`. Set `nps` to the "Speed for ..." your reference machine prints with its usual `-T`, so that time controls play unscaled there and proportionally longer on slower machines.

Uploaded PGNs are archived by a background thread. Hosts that do not allow threads in web apps, such as PythonAnywhere, never archive them, so leave Upload PGNs off there.

### Workers

Each worker needs Python 3.9+ with `pip install -r Client/requirements.txt`, `make`, a C++ compiler (`g++` or `clang++`), and the same token saved as `Client/credentials.stockfish_4pc`. Then, from `Client/`:

```
python client.py -U NAME -P PASSWORD -S http://SERVER:8000 -T 8 -N 1
```

- **Windows (MSYS2):** put `C:\msys64\ucrt64\bin` first on `PATH`, and `C:\msys64\usr\bin` (for `make`) last, then run the client with the full path to your Windows Python. If `ucrt64\bin` comes later, DLLs from other programs on `PATH` can make `g++` fail silently. MSYS2 also ships its own `python.exe`, which lacks the Client's packages.
- **Termux:** `pkg install python clang make`, then `pip install -r Client/requirements.txt`.

Every worker must produce the same `bench` node count for a given commit, since a mismatch stops the test. Check this on each new platform, e.g. ARM vs x86, before relying on it.

### Updating match.py

Copy `match.py` from the `cluster-runner` branch of the 4pc_arena fork into `Client/`, then bump `client_version` in `Config/config.json` and `CLIENT_VERSION` in `Client/worker.py` together. Workers then update themselves from `client_repo_url`, which must point at this fork.

---

OpenBench is an open-source Chess Engine Testing Framework for UCI engines. OpenBench provides a lightweight interface and client to facilitate running fixed-game tests as well as SPRT tests to benchmark changes to engines for performance and stability. OpenBench supports [Fischer Random Chess](https://en.wikipedia.org/wiki/Chess960).

OpenBench is the primary testing framework used for the development of [Ethereal.](https://github.com/AndyGrant/Ethereal) The primary instance of OpenBench can be found at [http://chess.grantnet.us](http://chess.grantnet.us/). The Primary instance of OpenBench supports development for
[Berserk](https://github.com/jhonnold/berserk), [Bit-Genie](https://github.com/Aryan1508/Bit-Genie), [BlackMarlin](https://github.com/dsekercioglu/blackmarlin), [Demolito](https://github.com/lucasart/Demolito), [Drofa](https://github.com/justNo4b/Drofa), [Ethereal](https://github.com/AndyGrant/Ethereal), [FabChess](https://github.com/fabianvdW/FabChess), [Halogen](https://github.com/KierenP/Halogen), [Igel](https://github.com/vshcherbyna/igel), [Koivisto](https://github.com/Luecx/Koivisto), [Laser](https://github.com/jeffreyan11/laser-chess-engine), [RubiChess](https://github.com/Matthies/RubiChess), [Seer](https://github.com/connormcmonigle/seer-nnue), [Stash](https://github.com/mhouppin/stash-bot), [Weiss](https://github.com/TerjeKir/weiss), [Winter](https://github.com/rosenthj/Winter), and [Zahak](https://github.com/amanjpro/zahak). A dozen or more engines are using their own private, local instances of OpenBench.

You can join OpenBench's [Discord server](https://discord.com/invite/9MVg7fBTpM) to join the discussion, see what developers are working on and talking about, or to find out how you can contribute to the project and become a part of it. OpenBench is heavily inspired by [Fishtest](https://github.com/glinscott/fishtest). The project is powered by the [Django Web Framework](https://www.djangoproject.com/) and [fastchess](https://github.com/Disservin/fastchess).

Documentation for OpenBench is available in the [Wiki](https://github.com/AndyGrant/OpenBench/wiki)
