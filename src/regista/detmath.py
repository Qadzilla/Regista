"""exp, log, sin, cos and hypot that give the same bits on every platform, for the league generator.

``math.exp`` and friends call the C library's libm, and libms differ in the last bit: macOS's and glibc's (Linux, where
CI and the live app run) disagree on about 4% of the ``sin``/``cos`` calls ``random.gauss`` makes and on a fraction of a
percent of ``exp``/``log`` calls (measured on a league match, 2026-10-24); glibc even picks a different routine on CPUs
with FMA. A last-bit difference is usually absorbed, but now and then it tips a ``rng.random() < p`` comparison, and the
match that follows is a different match: the same league fixture gave a different event stream on Linux than on a Mac.

These are ports of fdlibm's (Sun's freely distributable libm, also FreeBSD's): range reduction plus a fixed polynomial,
written with nothing but IEEE-754 double ``+ - * /``, ``math.sqrt`` (correctly rounded on every platform, as IEEE-754
requires), ``math.frexp``/``math.ldexp`` (exact) and ``math.floor``. Python rounds every operation to double (it never
fuses a multiply and an add across operations), so each function returns the same double on any machine and any
Python version. Accuracy is fdlibm's: under one unit in the last place.

``hypot`` is ``sqrt(x*x + y*y)``: CPython's ``math.hypot`` is its own careful algorithm, correctly rounded nearly
always, but compiled C, so not guaranteed to round alike everywhere either; the league's coordinates (metres, under
200) are far from overflow.

Only league mode uses this module (``MatchSim.m``); without ratings the generator keeps ``math`` and ``random.Random``,
so its output stays byte-identical to what it always was.
"""

from __future__ import annotations

import math
import random

__all__ = ["exp", "log", "sin", "cos", "hypot", "sqrt", "pi", "Random"]

pi = math.pi
sqrt = math.sqrt
_frexp, _ldexp, _floor = math.frexp, math.ldexp, math.floor

# ------------------------------------------------------------------------------------------------------------- exp
_O_THRESHOLD = 7.09782712893383973096e+02
_U_THRESHOLD = -7.45133219101941108420e+02
_LN2_HI = 6.93147180369123816490e-01      # ln 2, high part: its trailing bits are zero, so k * _LN2_HI is exact
_LN2_LO = 1.90821492927058770002e-10
_INV_LN2 = 1.44269504088896338700e+00
_P1 = 1.66666666666666019037e-01
_P2 = -2.77777777770155933842e-03
_P3 = 6.61375632143793436117e-05
_P4 = -1.65339022054652515390e-06
_P5 = 4.13813679705723846039e-08


def exp(x: float) -> float:
    """e**x (fdlibm e_exp.c)."""
    x = float(x)
    if x != x:
        return x
    if x > _O_THRESHOLD:
        raise OverflowError("math range error")
    if x < _U_THRESHOLD:
        return 0.0
    ax = -x if x < 0 else x
    if ax > 0.34657359027997264:              # |x| > ln2 / 2: reduce, x = k ln2 + r with |r| <= ln2 / 2
        if ax < 1.0397207708399179:           # |x| < 1.5 ln2
            k = 1 if x > 0 else -1
            hi = x - _LN2_HI if k == 1 else x + _LN2_HI
            lo = _LN2_LO if k == 1 else -_LN2_LO
        else:
            k = int(_INV_LN2 * x + (0.5 if x > 0 else -0.5))   # int() truncates toward zero, as fdlibm's cast does
            hi = x - k * _LN2_HI
            lo = k * _LN2_LO
        r = hi - lo
    elif ax < 3.725290298461914e-09:          # |x| < 2**-28
        return 1.0 + x
    else:
        k, hi, lo, r = 0, 0.0, 0.0, x
    t = r * r
    c = r - t * (_P1 + t * (_P2 + t * (_P3 + t * (_P4 + t * _P5))))
    if k == 0:
        return 1.0 - ((r * c) / (c - 2.0) - r)
    y = 1.0 - ((lo - (r * c) / (2.0 - c)) - hi)
    return _ldexp(y, k)


# ------------------------------------------------------------------------------------------------------------- log
_LG1 = 6.666666666666735130e-01
_LG2 = 3.999999999940941908e-01
_LG3 = 2.857142874366239149e-01
_LG4 = 2.222219843214978396e-01
_LG5 = 1.818357216161805012e-01
_LG6 = 1.531383769920937332e-01
_LG7 = 1.479819860511658591e-01
_SQRT1_2 = 0.7071067811865476


def log(x: float) -> float:
    """Natural logarithm (fdlibm e_log.c's polynomial; ``frexp`` splits x = 2**k * m exactly)."""
    x = float(x)
    if x != x:
        return x
    if x <= 0.0:
        raise ValueError("math domain error")
    if x == math.inf:
        return x
    m, k = _frexp(x)                           # x = m * 2**k, 0.5 <= m < 1, exact
    if m < _SQRT1_2:                           # bring m into [sqrt(2)/2, sqrt(2))
        m *= 2.0
        k -= 1
    f = m - 1.0                                # exact (Sterbenz)
    s = f / (2.0 + f)
    z = s * s
    w = z * z
    t1 = w * (_LG2 + w * (_LG4 + w * _LG6))
    t2 = z * (_LG1 + w * (_LG3 + w * (_LG5 + w * _LG7)))
    r = t2 + t1
    hfsq = 0.5 * f * f
    return k * _LN2_HI - ((hfsq - (s * (hfsq + r) + k * _LN2_LO)) - f)


# ------------------------------------------------------------------------------------------------------- sin, cos
_S1 = -1.66666666666666324348e-01
_S2 = 8.33333333332248946124e-03
_S3 = -1.98412698298579493134e-04
_S4 = 2.75573137070700676789e-06
_S5 = -2.50507602534068634195e-08
_S6 = 1.58969099521155010221e-10
_C1 = 4.16666666666666019037e-02
_C2 = -1.38888888888741095749e-03
_C3 = 2.48015872894767294178e-05
_C4 = -2.75573143513906633035e-07
_C5 = 2.08757232129817482790e-09
_C6 = -1.13596475577881948265e-11
_INV_PIO2 = 6.36619772367581382433e-01
_PIO2_1 = 1.57079632673412561417e+00       # first 33 bits of pi/2: n * _PIO2_1 is exact for |n| < 2**20
_PIO2_1T = 6.07710050650619224932e-11      # pi/2 - _PIO2_1
_PIO2_2 = 6.07710050630396597660e-11       # second 33 bits
_PIO2_2T = 2.02226624879595063154e-21      # pi/2 - (_PIO2_1 + _PIO2_2)
_PIO4 = 7.85398163397448278999e-01
_MAX_REDUCE = 4.0e5                         # |x| beyond this would need fdlibm's long reduction; nothing here comes close


def _ksin(x: float, y: float) -> float:
    """sin(x + y) for |x + y| <= pi/4, y the tail of x (fdlibm k_sin.c)."""
    z = x * x
    v = z * x
    r = _S2 + z * (_S3 + z * (_S4 + z * (_S5 + z * _S6)))
    return x - ((z * (0.5 * y - v * r) - y) - v * _S1)


def _kcos(x: float, y: float) -> float:
    """cos(x + y) for |x + y| <= pi/4 (FreeBSD k_cos.c)."""
    z = x * x
    w = z * z
    r = z * (_C1 + z * (_C2 + z * _C3)) + w * w * (_C4 + z * (_C5 + z * _C6))
    hz = 0.5 * z
    w = 1.0 - hz
    return w + (((1.0 - w) - hz) + (z * r - x * y))


def _reduce(x: float) -> tuple[int, float, float]:
    """x = n * pi/2 + (y0 + y1), |y0 + y1| <= pi/4 (fdlibm e_rem_pio2.c, medium arguments, two steps)."""
    if not -_MAX_REDUCE < x < _MAX_REDUCE:
        raise ValueError("argument too large for regista.detmath")
    n = _floor(x * _INV_PIO2 + 0.5)
    fn = float(n)
    t = x - fn * _PIO2_1                       # exact
    r = t - fn * _PIO2_2
    w = fn * _PIO2_2T - ((t - r) - fn * _PIO2_2)
    y0 = r - w
    y1 = (r - y0) - w
    return n, y0, y1


def sin(x: float) -> float:
    x = float(x)
    if x != x or x in (math.inf, -math.inf):
        return math.nan if x == x else x
    if -_PIO4 <= x <= _PIO4:
        return _ksin(x, 0.0)
    n, y0, y1 = _reduce(x)
    q = n & 3
    if q == 0:
        return _ksin(y0, y1)
    if q == 1:
        return _kcos(y0, y1)
    if q == 2:
        return -_ksin(y0, y1)
    return -_kcos(y0, y1)


def cos(x: float) -> float:
    x = float(x)
    if x != x or x in (math.inf, -math.inf):
        return math.nan if x == x else x
    if -_PIO4 <= x <= _PIO4:
        return _kcos(x, 0.0)
    n, y0, y1 = _reduce(x)
    q = n & 3
    if q == 0:
        return _kcos(y0, y1)
    if q == 1:
        return -_ksin(y0, y1)
    if q == 2:
        return -_kcos(y0, y1)
    return _ksin(y0, y1)


def hypot(x: float, y: float) -> float:
    return sqrt(x * x + y * y)


# ------------------------------------------------------------------------------------------------------- Random
_TWOPI = 2.0 * math.pi


class Random(random.Random):
    """``random.Random`` whose ``gauss`` uses the functions above instead of libm's.

    Same Mersenne Twister stream, same draws in the same order as CPython's ``gauss`` (Box-Muller, one pair per two
    calls, the second value cached in ``gauss_next``); only the transcendental functions are swapped. Every other
    method (``random``, ``uniform``, ``choice``, ``choices``) uses no libm and is platform-independent already."""

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        z = self.gauss_next
        self.gauss_next = None
        if z is None:
            x2pi = self.random() * _TWOPI
            g2rad = sqrt(-2.0 * log(1.0 - self.random()))
            z = cos(x2pi) * g2rad
            self.gauss_next = sin(x2pi) * g2rad
        return mu + z * sigma
