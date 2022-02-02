import copy
import random
import time
from typing import *

from wordly.game import make_guess
from wordly.word_pool import WordPool
from wordly.word_list import all_wordle_words, top_first_guesses

"""
The Solver suggests a next word based on all available information.

An optimal solver would generate a full possibility tree for all possible target words
and all available guesses. It minimizes the depth of the search tree. 
That would take days to run on a modern computer, even in a compiled language. [1]

So this solver relies on various heuristics to short-cut the process. 
Heuristics have near-optimal performance in practice [2].

As a human player, these strategies intuitive.
- Guess words that contain letters we haven't seen yet to maximize information gain.
- 

[1] https://www.poirrier.ca/notes/wordle/
[2] http://sonorouschocolate.com/notes/index.php?title=The_best_strategies_for_Wordle
"""
class Solver():
    def __init__(self, hard_mode=False, cost_exp=1.75, max_pool_size=5000, gt_ratio=1):
        self.hard_mode = hard_mode
        # targets represents the remaining possible solutions to a puzzle after applying guesses
        self.targets = WordPool()
        # "valids" contains the words that can be guessed. In Easy Mode, "valids" is the
        # whole Wordle dictionary; in Hard Mode it is a subset of that.
        self.valids = WordPool()
        self.freqs = {}
        for word, freq in all_wordle_words:
            self.freqs[word] = freq

        # params that control the heuristics
        # these have been tuned to produce the best results
        # while still solving the puzzle quickly
        self.cost_exp = cost_exp
        self.max_pool_size = max_pool_size
        self.gt_ratio = gt_ratio

    def get_next_words(self, guesses) -> List[Tuple[str, int]]:
        # Returns a list of good words to guess next

        # First guesses are pre-baked; otherwise that's a really long search
        # that's the same every game.
        if len(guesses) == 0:
            random.shuffle(top_first_guesses)
            return [(x, 1) for x in top_first_guesses]

        # apply guess feedback to eliminate invalid targets and valid guesses.
        self.targets.apply_guesses(guesses)
        if self.hard_mode:
            self.valids.apply_hardmode_constraints(guesses)

        # Handle edge case: if there are only two targets left, you don't want to pick
        # "any guess that reduces the target pool to 1", you want to pick
        # one of the two possible solutions, thereby profiting from the 50/50 chance
        # of guessing correctly.
        if len(self.targets.pool) <= 2:
            return [(random.choice(list(self.targets.pool)), 1)]

        # For non-first guesses, we'll do a search.
        # Ideally, we will try each combination of (valid word, target) and
        # find the one that most likely constrains the target pool to very few words.
        # If the guess and target pools are large, we do some heuristic
        # stuff to reduce or subsample the space before running the all-pairs search.
        targets_subset = copy.deepcopy(self.targets)
        valids_subset = copy.deepcopy(self.valids)
        pool_size = len(self.valids.pool) * len(self.targets.pool)

        # Each pair takes around 0.2ms to check, so we want to reduce pool_size to <= 5000.
        # Start by applying nonmatches from the guess results to the guesses pool. That will
        # encourage guessing of new letters.
        if pool_size > self.max_pool_size:
            # reduce valid guesses pool by removing words with nonmatching letters
            ls = list((k, v) for k, v in guesses.items())
            random.shuffle(ls)
            for guess, result in ls:
                if len(valids_subset.pool) * len(targets_subset.pool) <= self.max_pool_size:
                    # good enough
                    break
                before = copy.deepcopy(valids_subset)
                valids_subset.apply_nonmatches(guess, result)
                if len(valids_subset.pool) < 50:
                    # Over-constraining the guess pool leads to dumb guesses
                    # don't go too hard on this
                    valids_subset = before

        # Subsample the guess and target pools as needed to shrink from there.
        while pool_size > self.max_pool_size:
            if len(valids_subset.pool) >= len(targets_subset.pool) * self.gt_ratio:
                # reduce the guesses pool
                vpool = random.sample(list(valids_subset.pool),
                                      max(len(valids_subset.pool) // 2, 10)
                                      )
                valids_subset.remove_all_except(vpool)
            else:
                # reduce the targets pool
                tpool = random.sample(list(targets_subset.pool),
                                      max(len(targets_subset.pool)//2, 10)
                                      )
                targets_subset.remove_all_except(tpool)
            pool_size = len(targets_subset.pool) * len(valids_subset.pool)

        t0 = time.time()


        """
        if len(self.targets.pool) > 243:  # 3^5
            # If there are many targets, we can simply try all guess results.
            # There are 3^5 of those (each letter has 3 possible outcomes).
            for guess in guess_pool:
                guess_score = 0
                for result in ALL_POSSIBLE_RESULTS:
                    rstr = ''.join([guess[i] if result[i] == '*'
                                    else result[i]
                                    for i in range(len(result))])
                    new_guesses = {guess:rstr}
                    new_guesses.update(guesses)
                    targets_copy = copy.deepcopy(self.targets)
                    targets_copy.apply_guesses(new_guesses)
                    guess_score += len(targets_copy.pool)
                    if guess_score > best_score:
                        break
                if 0 < guess_score < best_score:
                    best_score = guess_score
                    guess_scores.append((guess, guess_score))
        else:
        """

        # now search all (valid guess, target) pairs to find the best guess from the
        # reduced pools.
        guess_scores = []
        best_score = float('inf')
        guess_pool = list(valids_subset.pool)
        targets_pool = list(targets_subset.pool)

        for guess in guess_pool:
            guess_score = 0
            guesses_copy = copy.deepcopy(guesses)
            for i, tw in enumerate(targets_pool):
                targets_copy = copy.deepcopy(targets_subset)
                new_guesses = {guess: make_guess(guess, tw)}
                new_guesses.update(guesses)
                n_before = len(targets_copy.pool)
                targets_copy.apply_guesses(new_guesses)
                n_left = len(targets_copy.pool)
                guess_score += n_left**self.cost_exp
                if guess_score > best_score:
                    # we already know this guess is worse than one we have
                    # bail outta this trial
                    break
            if guess_score < best_score:
                best_score = guess_score
                guess_scores.append((guess, round(guess_score, 3)))

        #print(len(valids_subset.pool), len(targets_subset.pool), pool_size, round(time.time()-t0, 3))
        guess_scores.sort(key=lambda x: x[1])
        return guess_scores

"""
Functions that use the Solver and its Dictionary
"""
def sanitize_validate_input(guesses:dict) -> dict:
    guesses_upper = {}
    for guess, result in guesses.items():
        guesses_upper[guess.upper()] = result.upper()
        assert len(guess) == 5
        assert len(result) == 5
        assert guess.isalpha()
        for c in result:
            assert c.isalpha() or c in ['.', '?']
    return guesses_upper


def recommend_next_words(guesses: dict, hard_mode=False) -> list:
    guesses = sanitize_validate_input(guesses)
    # run solver
    s = Solver(hard_mode)
    next_words = s.get_next_words(guesses)
    if len(next_words) > 10:
        return next_words[:10]
    else:
        return next_words
