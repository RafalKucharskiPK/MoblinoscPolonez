import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from dotmap import DotMap
import os
import math
import logging
import sys

LOG_LEVEL = logging.CRITICAL # logging.WARNING # logging.INFO #logging.WARNING #logging.CRITICAL

def init_logger():

    logging.basicConfig(stream=sys.stdout, format='%(asctime)s-%(levelname)s-%(message)s',
                            datefmt='%d-%m-%y %H:%M:%S', level=LOG_LEVEL)
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    return logging.getLogger(__name__)



def read_wichita(plot = False, logger = None):
    # reads the data from txtx files and store them in the disctionary as pandas dataFrames
    inData = DotMap()
    for file in os.listdir('./wichita'):
        if file.startswith('wichita'):
            df = pd.read_csv('wichita/{}'.format(file), header=None)

            df = pd.DataFrame(df.values.reshape(464, int(df.shape[0] / 464)))
            logger.info(file[8:-4], df.shape) if logger else None
            inData[file[8:-4]] = df
    return inData


def doubly_constrained(S, D, Q, C = None, X=None, beta=0.1, max_ite=10000, eps=0.01, normalize=True, logger = None):
    """
    :param S: pandas series of origin flow from each zone
    :param D: pandas series of destination flows towards each zone
    :param Q: cost matrix (distance) between the zones (pd.DataFrame)
    :param C: balancing matrix for triply constrained model - by default np.ones
    :param X: original flow matrix - by default np.ones
    :param beta: - parameter of impedance
    :param max_ite: number of iterations to balance the matrix
    :param eps: maximimal allowed error at origins and destinations
    :param normalize: do we need to normalize S to D or are they balanced?
    :param logger:
    :return: matrix meeting the O, D constrains and following spatial distribution
    """

    if normalize: # see if sums match
        D = D * (S.sum() / D.sum())  # adjust D to O

    def fun(x): # create impedance function from distance matrix
        return np.exp(-beta * x)

    S = S.values  # rows
    A = np.ones_like(S)  # balancing factor for origins
    D = D.values  # columns
    B = np.ones_like(D)  # balancing factor for destinations
    costs = Q.copy() # to report
    Q = Q.apply(np.vectorize(fun))  # cost function matrix
    if C is None:
        C = np.ones((len(S), len(D))) # without triply balancing
    if X is None:
        X = np.ones((len(S), len(D))) # without triply balancing

    # main loop
    for i in range(max_ite): # balance
        T = np.outer(S * A, D * B) * Q * C * X # create matrix
        A = np.reciprocal((B * D * Q * C * X).sum(1)) # update balancing for rows
        T = np.outer(S * A, D * B) * Q * C * X # compute matrix
        B = np.reciprocal((A * S * (Q * C * X).T).sum(1)) # update balancing for columns
        if max(((T.sum(1) - S) ** 2).sum(), ((T.sum(0) - D) ** 2).sum()) < eps: # see if converged
            break
        if logger and i % 1 == 0:
            logger.info("Iteration: {}\t total: {:.2f}\t "
                  "error_O: {:.2f}\t error_D: {:.2f}".format(i,
                                                             T.sum().sum(),
                                                             ((T.sum(1) - S) ** 2).sum(),
                                                             ((T.sum(0) - D) ** 2).sum()))

    T_c = np.outer(S * A, D * B) * Q # for triply constrained

    #compute hists
    H = T.stack().to_frame()
    H.columns = ['flow']
    H['cost'] = costs.stack()
    mean_cost = (H.cost * H.flow).sum() / H.flow.sum()
    cost_var = (H.cost * H.flow).std()
    if logger:
        logger.warning(
            "Inner ite: {}\t demand:{:.2f}\t trips: {:.2f}\t error_O: {:.2f}\t error_D: {:.2f} cost mean: {:.2f}\t var: {:.2f}".format(
                i,
                S.sum(),
                T.sum().sum(),
                ((T.sum(1) - S) ** 2).sum(),
                ((T.sum(0) - D) ** 2).sum(),
                mean_cost, cost_var))
    if logger.level == logging.INFO:
        fig, axes = plt.subplots(1, 4, figsize=(15, 3))
        axes = axes.flatten()
        # productions
        ((T.sum(1) - S) / S).hist(ax=axes[0])  # error at origins
        axes[0].set_title('Error at origins deistibution')
        ((T.sum(0) - D) / D).hist(ax=axes[1])  # error at destinations
        axes[1].set_title('Error at destinations deistibution')
        H['cost'].plot(kind='hist', weights=H['flow'], ax=axes[2], bins=30)  # trip distance distribution
        axes[2].set_title('Trip distance distribution')

        x = np.linspace(Q.min().min(), Q.max().max(), 200)
        axes[3].plot(x, fun(x))
        axes[3].set_title('Theoretical impedance')

    return {"T":T,"T_c":T_c}  # two outputs for triply constrained model


def triply_constrained(inData, k_s = [1,2,3], max_ite = 10000, eps=0.01, logger = None, beta = 0.1):
    """
    computed doubly constrained model for each subgroup
    and balances until the total matrix meets the desired criteria.
    :param inData: S, D, X for each k, distance matrix - use read_wichita()
    :param k_s: groups
    :param max_ite: number of iterations to balance
    :param eps: maximal allowed error
    :param logger:
    :return: k matrices
    """

    X_k = dict()  # output trip matrix per each k
    X = inData.full_xij # original trip matrix
    C = np.ones_like(X) # balancing matrix
    Q = inData.dist # cost matrix (distances)
    for i in range(max_ite):  # balance
        for k in k_s:
            Xij_k = inData['full_xij_k{}'.format(k)] # matrix to balance
            S = Xij_k.sum(axis=1) # sources (productions)
            D = Xij_k.sum(axis=0) # destinations (attractions)
            X_k[k] = doubly_constrained(S, D, Q, C, X, beta=beta,
                                        max_ite = max_ite, eps = eps, logger = logger) # compute the matrix
        X_ij = sum([X_k[k]['T'] for k in k_s]) # total matrix - sum over k
        err = ((X_ij - X)**2).sum().sum() # error - sum of squares
        if err <= eps:
            logger.critical("Converged Ite: {}\t error:{:.2f}\t". format(i,err))
            break
        if logger:
            logger.error("Outer ite: {}\t error:{:.2f}\t". format(i,err))
        # update matrix -
        C = np.reciprocal(sum([X_k[k]['T_c'] for k in k_s]))
    return dict(zip(k_s, [X_k[k]['T'] for k in k_s]))


def pipe():
    logger = init_logger()
    inData = read_wichita(plot=False, logger = logger)  # read matrices and distances from txt files
    return triply_constrained(inData, logger = logger)




if __name__ == "__main__":
    pipe()


