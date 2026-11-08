# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# The implementation for PentanomialSPRT is taken directly from Fishtest.
# The implementation for TrinomialSPRT was derived directory from Fishtest.
#
# Only three functions should be used externally from this Module.
# 1. llr = TrinomialSPRT([losses, draws, wins], elo0, elo1)
# 2. llr = PentanomialSPRT([ll, ld, dd, dw, ww], elo0, elo1)
# 3. lower, elo, upper = Elo((L, D, W) or (LL, LD, DD/WL, DW, WW))

import math
import scipy.stats
from scipy import optimize

def TrinomialSPRT(results, elo0, elo1):

    # Needs at least 1 Loss, 1 Draw, and 1 Win
    if any(not x for x in results):
        return 0.00

    N   = sum(results)
    pdf = [x / N for x in results]

    # Estimated draw elo based on PDF of LDW
    elo, drawelo = proba_to_bayeselo(*pdf)

    # Probability laws under H0 and H1
    pdf0 = bayeselo_to_proba(elo0, drawelo)
    pdf1 = bayeselo_to_proba(elo1, drawelo)

    # Log-Likelyhood Ratio
    return sum([results[i] * math.log(pdf1[i] / pdf0[i]) for i in range(3)])

def PentanomialSPRT(results, elo0, elo1):

    ## Implements https://hardy.uhasselt.be/Fishtest/normalized_elo_practical.pdf

    # Ensure no division by 0 issues
    results = [max(1e-3, x) for x in results]

    # Partial computation of Normalized t-value
    nelo_divided_by_nt = 800 / math.log(10)
    nt0, nt1 = (x / nelo_divided_by_nt for x in (elo0, elo1))
    t0, t1 = nt0 * math.sqrt(2), nt1 * math.sqrt(2)

    # Number of game-pairs, and the PDF of Ptnml(0-2) expressed as (0-1)
    N = sum(results)
    pdf = [(i / 4, results[i] / N) for i in range(0, 5)]

    # Pdf given each normalized t-value, and then the LLR process for each
    pdf0, pdf1 = (MLE_tvalue(pdf, 0.5, t) for t in (t0, t1))
    mle_pdf    = [(math.log(pdf1[i][1]) - math.log(pdf0[i][1]), pdf[i][1]) for i in range(len(pdf))]

    return N * stats(mle_pdf)[0]

def Elo(results):

    # Cannot compute elo without any games
    if not (N := sum(results)) or N == 1:
        return (0.00, 0.00, 0.00)

    div = len(results) - 1 # Converts index to the points outcome
    mu  = sum((f / div) * results[f] for f in range(len(results))) / N
    var = sum(((f / div) - mu)**2 * results[f] for f in range(len(results))) / N
    df  = N - 1 # Degrees of freedom

    mu_min = mu + scipy.stats.t.ppf(0.025, df) * math.sqrt(var) / math.sqrt(N)
    mu_max = mu + scipy.stats.t.ppf(0.975, df) * math.sqrt(var) / math.sqrt(N)

    return logistic_elo(mu_min), logistic_elo(mu), logistic_elo(mu_max)


def bayeselo_to_proba(elo, draw_elo):
    pwin  = 1.0 / (1.0 + math.pow(10.0, (-elo + draw_elo) / 400.0))
    ploss = 1.0 / (1.0 + math.pow(10.0, ( elo + draw_elo) / 400.0))
    pdraw = 1.0 - pwin - ploss
    return (ploss, pdraw, pwin)

def proba_to_bayeselo(ploss, pdraw, pwin):
    elo      = 200 * math.log10(pwin/ploss * (1-ploss)/(1-pwin))
    draw_elo = 200 * math.log10((1-ploss)/ploss * (1-pwin)/pwin)
    return (elo, draw_elo)


def secular(pdf):
    """
    Solves the secular equation sum_i pi*ai/(1+x*ai)=0.
    """
    epsilon = 1e-9
    v, w = pdf[0][0], pdf[-1][0]
    values = [ai for ai, pi in pdf]
    v = min(values)
    w = max(values)
    assert v * w < 0
    l = -1 / w
    u = -1 / v

    def f(x):
        return sum([pi * ai / (1 + x * ai) for ai, pi in pdf])

    x, res = optimize.brentq(
        f, l + epsilon, u - epsilon, full_output=True, disp=False
    )
    assert res.converged
    return x

def stats(pdf):
    epsilon = 1e-6
    for i in pdf:
        assert -epsilon <= i[1] <= 1 + epsilon
    n = sum([prob for value, prob in pdf])
    assert abs(n - 1) < epsilon
    s = sum([prob * value for value, prob in pdf])
    var = sum([prob * (value - s) ** 2 for value, prob in pdf])
    return s, var

def uniform(pdf):
    n = len(pdf)
    return [(ai, 1 / n) for ai, pi in pdf]

def MLE_tvalue(pdfhat, ref, s):

    N = len(pdfhat)
    pdf_MLE = uniform(pdfhat)
    for i in range(10):
        pdf_ = pdf_MLE
        mu, var = stats(pdf_MLE)
        sigma = var ** (1 / 2)
        pdf1 = [
            (ai - ref - s * sigma * (1 + ((mu - ai) / sigma) ** 2) / 2, pi)
            for ai, pi in pdfhat
        ]
        x = secular(pdf1)
        pdf_MLE = [
            (pdfhat[i][0], pdfhat[i][1] / (1 + x * pdf1[i][0])) for i in range(N)
        ]
        if max([abs(pdf_[i][1] - pdf_MLE[i][1]) for i in range(N)]) < 1e-9:
            break

    return pdf_MLE


def logistic_elo(x):
    x = min(max(x, 1e-3), 1-1e-3)
    return -400 * math.log10(1 / x - 1)


# FFA (4-player free-for-all), as in the engine repo's tools/ffa_match.py. A sample is the pairwise
# placement score of one group of 4 games (Dev in each seat once, against 3 Base copies): every
# (Dev seat, Base seat) pair scores 1 if Dev finished with more points, 0.5 if equal, 0 if fewer.
# Bounds are logistic Elo of that score. Tests keep only the count, sum and sum of squares.

FFA_MIN_GROUPS = 20   # no verdict before this many groups
FFA_VAR_FLOOR  = 0.01 # about the variance of 12 independent pairwise results

def ffa_elo_to_score(elo):
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))

def ffa_score_to_elo(s):
    s = min(max(s, 1e-6), 1 - 1e-6)
    return -400.0 * math.log10(1.0 / s - 1.0)

def FfaSPRT(n, total, totalsq, elo0, elo1):

    # GSPRT with the normal approximation and the samples' own variance (with a floor)
    if n < 2:
        return 0.0

    mean = total / n
    var  = max(totalsq / n - mean * mean, FFA_VAR_FLOOR)
    s0, s1 = ffa_elo_to_score(elo0), ffa_elo_to_score(elo1)

    return n * ((mean - s0) ** 2 - (mean - s1) ** 2) / (2 * var)

def FfaElo(n, total, totalsq):

    # Returns (lower, elo, upper): the 95% interval from the sample standard deviation
    if n < 1:
        return (0.0, 0.0, 0.0)

    mean = total / n
    sd   = math.sqrt(max(0.0, (totalsq - n * mean * mean) / (n - 1))) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.5

    lower = ffa_score_to_elo(max(1e-6, mean - half))
    upper = ffa_score_to_elo(min(1 - 1e-6, mean + half))
    return (lower, ffa_score_to_elo(mean), upper)


if __name__ == '__main__':

    R3 = (22569, 44137, 22976)
    R5 = (39, 8843, 26675, 9240, 44)
    elo0, elo1 = (0.50, 2.50)

    print (PentanomialSPRT(R5, elo0, elo1))
    print (TrinomialSPRT(R3, elo0, elo1))
