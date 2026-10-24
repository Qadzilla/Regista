"""regista.detmath: the league generator's exp, log, sin, cos, hypot and Gaussians give the same bits on every platform.

The golden values below were computed on macOS (arm64, Python 3.13); CI runs them on Linux (x86-64, Python 3.11), the
platform the live app builds the league on. A failure here means some platform rounds these functions differently, and
league matches would differ between machines (as they did with libm before 0.7.1: docs/scout-terminal/build/determinism.md).
"""

from __future__ import annotations

import math
import random

import pytest

from regista import detmath

GOLDEN = [
    ('exp', '0x1.54c629b4acad8p+2', '0x1.9aa67c5399abep+7'),
    ('exp', '0x1.b20a3e51d12b0p+3', '0x1.7b9ae620aae1cp+19'),
    ('exp', '-0x1.7029cb843a6fep+3', '0x1.522e04b7f34acp-17'),
    ('exp', '-0x1.cdf8e0a906b76p+4', '0x1.4516b1775dad8p-42'),
    ('exp', '0x1.912366ff96330p+0', '0x1.32b00458fce90p+2'),
    ('exp', '0x1.0147a25762b58p+4', '0x1.25c3e9b0de739p+23'),
    ('log', '0x1.a73e1e9e3b652p+11', '0x1.04138e568ae90p+3'),
    ('log', '0x1.7a16ae2826f10p+0', '0x1.8f4f5774bb98bp-2'),
    ('log', '0x1.7ab83228b8ec3p-1', '-0x1.34c3f479bb878p-2'),
    ('log', '0x1.5fe6f9bd36402p+0', '0x1.45cfed25ff5e9p-2'),
    ('log', '0x1.db4142475bdbep-1', '-0x1.310ae944e4b3ap-4'),
    ('log', '0x1.843c2fb8a92a7p+11', '0x1.01504d9cf3148p+3'),
    ('sin', '0x1.04ed657409650p+0', '0x1.b413d7a36d48ap-1'),
    ('sin', '0x1.b24f671ebc3b8p+0', '0x1.fbf567d1a1cc7p-1'),
    ('sin', '0x1.768fd8c3e1145p+2', '-0x1.ab7c5f4932125p-2'),
    ('sin', '0x1.27f7cebd8a3d8p+1', '0x1.7997f94c22280p-1'),
    ('sin', '0x1.1011f8f1b61dfp+2', '-0x1.ca7c1ce111fbdp-1'),
    ('sin', '0x1.ad762a81809b2p-3', '0x1.aa522edbd1bc7p-3'),
    ('cos', '0x1.be66f103e8a7ep+1', '-0x1.e1aba2b99de0bp-1'),
    ('cos', '0x1.8a8f9d7c00798p+2', '0x1.fc6dea03c0a32p-1'),
    ('cos', '0x1.7014447828fa4p+1', '-0x1.edff1a60fdec9p-1'),
    ('cos', '0x1.5fa5145cad893p+2', '0x1.68d42713db2a9p-1'),
    ('cos', '0x1.d6f395f7154bcp-3', '0x1.f285b1594f9f9p-1'),
    ('cos', '0x1.38e62d0fab18ap+0', '0x1.5db7882e4cc5fp-2'),
    ('hypot', ('-0x1.63815e62a1a00p-2', '0x1.1b3928226504cp+4'), '0x1.1b4719ab33766p+4'),
    ('hypot', ('0x1.98094cfa190a8p+3', '0x1.318a69745bc70p+2'), '0x1.b3b297ba71f26p+3'),
    ('hypot', ('0x1.0fad775fe64d0p+5', '0x1.0e08b880a3078p+6'), '0x1.2e4691d7d3132p+6'),
]
GAUSS_2026 = ['0x1.bb53a07efeeafp-1', '0x1.9bb8c75d28bdcp-1', '-0x1.fa3e959500174p+0', '-0x1.2d6717ef47b3ap-3', '0x1.22e08b85fae66p-1', '0x1.b593804f6d083p-2']


@pytest.mark.parametrize("name,x,want", GOLDEN)
def test_the_same_bits_as_recorded(name, x, want):
    args = [float.fromhex(a) for a in x] if isinstance(x, tuple) else [float.fromhex(x)]
    assert getattr(detmath, name)(*args).hex() == want


def test_gaussians_are_the_same_bits_as_recorded_and_use_the_same_draws_as_random():
    g = detmath.Random(2026)
    assert [g.gauss(0.0, 1.0).hex() for _ in range(6)] == GAUSS_2026
    # same Mersenne Twister draws, in the same order, as CPython's gauss: the streams stay in step after any number of calls
    a, b = detmath.Random(5), random.Random(5)
    for _ in range(101):
        assert abs(a.gauss(1.0, 2.0) - b.gauss(1.0, 2.0)) < 1e-12
    assert a.random() == b.random()


def test_within_a_unit_in_the_last_place_or_two_of_libm():
    """fdlibm's accuracy (under 1 ulp of the true value; libm is within 1 ulp too), across the ranges the league uses."""
    r = random.Random(3)
    for _ in range(20000):
        for name, x in (("exp", r.uniform(-40, 40)), ("log", r.uniform(1e-12, 1e6)), ("sin", r.uniform(-7, 7)),
                        ("cos", r.uniform(-7, 7))):
            want = getattr(math, name)(x)
            assert abs(getattr(detmath, name)(x) - want) <= 2 * math.ulp(want), (name, x)
        a, b = r.uniform(-200, 200), r.uniform(-200, 200)
        assert abs(detmath.hypot(a, b) - math.hypot(a, b)) <= 2 * math.ulp(math.hypot(a, b))


def test_edges():
    assert detmath.exp(0.0) == 1.0 and detmath.log(1.0) == 0.0 and detmath.sin(0.0) == 0.0 and detmath.cos(0.0) == 1.0
    assert detmath.exp(-1000.0) == 0.0 and math.isnan(detmath.exp(math.nan)) and detmath.log(math.inf) == math.inf
    with pytest.raises(OverflowError):
        detmath.exp(1000.0)
    with pytest.raises(ValueError):
        detmath.log(0.0)
    with pytest.raises(ValueError):
        detmath.sin(1e9)


def test_the_league_generator_calls_no_libm_function(monkeypatch):
    """A league match runs on detmath alone: every libm function the generator could reach is booby-trapped."""
    import pathlib

    from regista.season.league import generate_kwargs, load_league
    from regista.synth import generator

    league = load_league(pathlib.Path(__file__).resolve().parents[1] / "data" / "season" / "league.json")

    def trap(*_a):
        raise AssertionError("libm called in league mode")

    for name in ("exp", "log", "log2", "log10", "log1p", "expm1", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
                 "sinh", "cosh", "tanh", "pow", "hypot", "dist", "erf", "erfc", "gamma", "lgamma"):
        monkeypatch.setattr(math, name, trap)
    for name in ("_log", "_cos", "_sin", "_exp"):
        if hasattr(random, name):
            monkeypatch.setattr(random, name, trap)
    kw = generate_kwargs(league, league["fixtures"][0])
    generator.generate(**{**kw, "minutes": 2.0})
