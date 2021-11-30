"""Lite graph objects used by pecanpy."""

import numpy as np
from numba import jit
from pecanpy.graph import DenseGraph


class DenseRWGraph(DenseGraph):
    """Dense Graph object that stores graph as array.

    Examples:
        Read ``.npz`` files and create ``DenseGraph`` object using ``read_npz``.

        >>> from pecanpy.graph import DenseGraph
        >>> g = DenseGraph() # initialize DenseGraph object
        >>> g.read_npz(paht_to_npz_file, weighted=True, directed=False)

        Read ``.edg`` files and create ``DenseGraph`` object using ``read_edg``.

        >>> from pecanpy.graph import DenseGraph
        >>>
        >>> # initialize DenseGraph object
        >>> g = DenseGraph()
        >>>
        >>> # read graph from edgelist
        >>> g.read_edg(path_to_edg_file, weighted=True, directed=False)
        >>>
        >>> # save the dense graph as npz file to be used later
        >>> g.save(npz_outpath)

    """

    def get_average_weights(self):
        """Compute average edge weights."""
        deg_ary = self.data.sum(axis=1)
        n_nbrs_ary = self.nonzero.sum(axis=1)
        return deg_ary / n_nbrs_ary

    def get_has_nbrs(self):
        """Wrap ``has_nbrs``."""
        nonzero = self.nonzero

        @jit(nopython=True, nogil=True)
        def has_nbrs(idx):
            for j in range(nonzero.shape[1]):
                if nonzero[idx, j]:
                    return True
            return False

        return has_nbrs

    @staticmethod
    @jit(nopython=True, nogil=True)
    def get_normalized_probs(
        data,
        nonzero,
        p,
        q,
        cur_idx,
        prev_idx,
        average_weight_ary,
    ):
        """Calculate node2vec transition probabilities.

        Calculate 2nd order transition probabilities by first finidng the
        neighbors of the current state that are not reachable from the previous
        state, and devide the according edge weights by the in-out parameter
        ``q``. Then devide the edge weight from previous state by the return
        parameter ``p``. Finally, the transition probabilities are computed by
        normalizing the biased edge weights.

        Note:
            If ``prev_idx`` present, calculate 2nd order biased transition,
        otherwise calculate 1st order transition.

        """
        nbrs_ind = nonzero[cur_idx]
        unnormalized_probs = data[cur_idx].copy()

        if prev_idx is not None:  # 2nd order biased walks
            non_com_nbr = np.logical_and(
                nbrs_ind,
                ~nonzero[prev_idx],
            )  # nbrs of cur but not prev
            non_com_nbr[prev_idx] = False  # exclude previous state from out biases

            unnormalized_probs[non_com_nbr] /= q  # apply out biases
            unnormalized_probs[prev_idx] /= p  # apply the return bias

        unnormalized_probs = unnormalized_probs[nbrs_ind]
        normalized_probs = unnormalized_probs / unnormalized_probs.sum()

        return normalized_probs

    @staticmethod
    @jit(nopython=True, nogil=True)
    def get_extended_normalized_probs(
        data,
        nonzero,
        p,
        q,
        cur_idx,
        prev_idx,
        average_weight_ary,
    ):
        """Calculate node2vec+ transition probabilities."""
        cur_nbrs_ind = nonzero[cur_idx]
        unnormalized_probs = data[cur_idx].copy()

        if prev_idx is not None:  # 2nd order biased walks
            prev_nbrs_weight = data[prev_idx].copy()

            inout_ind = cur_nbrs_ind & (prev_nbrs_weight < average_weight_ary)
            inout_ind[prev_idx] = False  # exclude previous state from out biases

            # print("CURRENT: ", cur_idx)
            # print("INOUT: ", np.where(inout_ind)[0])
            # print("NUM INOUT: ", inout_ind.sum(), "\n")

            t = prev_nbrs_weight[inout_ind] / average_weight_ary[inout_ind]
            # b = 1; t = b * t / (1 - (b - 1) * t)  # optional nonlinear parameterization

            # compute out biases
            alpha = 1 / q + (1 - 1 / q) * t

            # suppress noisy edges
            alpha[
                unnormalized_probs[inout_ind] < average_weight_ary[cur_idx]
            ] = np.minimum(1, 1 / q)
            unnormalized_probs[inout_ind] *= alpha  # apply out biases
            unnormalized_probs[prev_idx] /= p  # apply  the return bias

        unnormalized_probs = unnormalized_probs[cur_nbrs_ind]
        normalized_probs = unnormalized_probs / unnormalized_probs.sum()

        return normalized_probs