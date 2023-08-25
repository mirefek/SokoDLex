import numpy as np

def np_all_positions(shape):
    return np.moveaxis(np.indices(shape), 0, -1)
def positions_true(a):
    return tuple(map(tuple, np_all_positions(a.shape)[a]))

def np_softmax(v):
    v = np.array(v)-np.max(v)
    v = np.exp(v)
    v /= np.sum(v)
    return v
def np_random_categ(probs):
    res = np.sum(np.cumsum(probs) < np.random.random())
    return min(res, len(probs)-1)

def binom(n, k):
    if k < 0 or k > n: return 0
    result = 1
    for i in range(min(k, n-k)):
        result *= n-i
        result //= i+1
    return result

def filtermap(f, it):
    for x in it:
        y = f(x)
        if y is not None: yield y

def maybe_next(it):
    try:
        return next(it)
    except StopIteration:
        return None

def remove_suffix(s, suffix):
    if not suffix: return s
    if not s.endswith(suffix): return None
    return s[:-len(suffix)]
def remove_prefix(s, prefix):
    if not prefix: return s
    if not s.startswith(prefix): return None
    return s[len(prefix):]
