#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Hierarchical Dirichlet Process - Latent Dirichlet Allocation
# This code is available under the MIT License.
# (c)2010-2011 Nakatani Shuyo / Cybozu Labs Inc.
# (refer to "Hierarchical Dirichlet Processes"(Teh et.al, 2005))

import numpy

class HDPLDA:
    def __init__(self, alpha, gamma, beta, docs, V):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.V = V
        self.M = len(docs)

        # t : table index for document j
        #     t=0 means to draw a new table
        self.using_t = [[0] for j in xrange(self.M)]

        # k : dish index
        #     k=0 means to draw a new dish
        self.using_k = [0]

        self.x_ji = docs # vocabulary for each document and term
        self.k_jt = [numpy.array([0] ,dtype=int) for j in xrange(self.M)]   # topic for each document and table
        self.n_jt = [numpy.array([0] ,dtype=int) for x_i in docs]           # number of terms for each document and table

        self.m_k = numpy.array([0] ,dtype=int)  # number of tables for each topic
        self.n_k = numpy.array([0] ,dtype=int)  # number of terms for each topic
        self.n_kv = [dict()]                    # number of terms for each topic and vocabulary

        #self.t_ji = [numpy.zeros(len(x_i), dtype=int) - 1 for x_i in docs] # table for each document and term (without assignment)

    def inference(self):
        for j, x_i in enumerate(self.x_ji):
            for i in range(len(x_i)):
                self.sampling_t(j, i)
            for t in self.tables[j]:
                self.sampling_k(j, t)

    def worddist(self):
        return [(self.n_kv[k] + self.beta) / (self.n_k[k] + self.Vbeta) for k in self.topics]

    def perplexity(self):
        phi = self.worddist()
        phi.append(numpy.zeros(self.V) + 1.0 / self.V)
        log_per = 0
        N = 0
        gamma_over_T_gamma = self.gamma / (self.n_tables + self.gamma)
        for j, x_i in enumerate(self.x_ji):
            p_k = numpy.zeros(self.m_k.size)    # topic dist for document 
            for t in self.tables[j]:
                k = self.k_jt[j][t]
                p_k[k] += self.n_jt[j][t]
            len_x_alpha = len(x_i) + self.alpha
            p_k /= len_x_alpha
            
            p_k_parent = self.alpha / len_x_alpha
            p_k += p_k_parent * (self.m_k / (self.n_tables + self.gamma))
            
            theta = [p_k[k] for k in self.topics]
            theta.append(p_k_parent * gamma_over_T_gamma)

            for v in x_i:
                log_per -= numpy.log(numpy.inner([p[v] for p in phi], theta))
            N += len(x_i)
        return numpy.exp(log_per / N)

    def dump(self, disp_x=False):
        if disp_x: print "x_ji:", self.x_ji
        print "t_ji:", self.t_ji
        print "k_jt:", self.k_jt
        print "n_kv:", self.n_kv
        print "n_jt:", self.n_jt
        print "n_k:", self.n_k
        print "m_k:", self.m_k


    # sampling t (table) from posterior
    def sampling_table(self, j, i):
        v = self.x_ji[j][i]
        tables = self.tables[j]
        t_old = self.t_ji[j][i]
        if t_old >=0:
            k_old = self.k_jt[j][t_old]

            # decrease counters
            self.n_kv[k_old, v] -= 1
            self.n_k[k_old] -= 1
            self.n_jt[j][t_old] -= 1

            if self.n_jt[j][t_old]==0:
                # table that all guests are gone
                tables.remove(t_old)
                self.m_k[k_old] -= 1
                self.n_tables -= 1
                self.updated_n_tables()

                if self.m_k[k_old] == 0:
                    # topic (dish) that all guests are gone
                    self.topics.remove(k_old)

        # sampling from posterior p(t_ji=t)
        t_new = self.sampling_t(j, i, v, tables)

        # increase counters
        self.t_ji[j][i] = t_new
        self.n_jt[j][t_new] += 1

        k_new = self.k_jt[j][t_new]
        self.n_k[k_new] += 1
        self.n_kv[k_new, v] += 1

    def sampling_t(self, j, i, v, tables):
        f_k = (self.n_kv[:, v] + self.beta) / (self.n_k + self.Vbeta)
        p_t = [self.n_jt[j][t] * f_k[self.k_jt[j][t]] for t in tables]
        p_x_ji = numpy.inner(self.m_k, f_k) + self.gamma_f_k_new_x_ji
        p_t.append(p_x_ji * self.alpha_over_T_gamma)

        p_t = numpy.array(p_t, copy=False)
        p_t /= p_t.sum()
        drawing = numpy.random.multinomial(1, p_t).argmax()
        if drawing < len(tables):
            return tables[drawing]
        else:
            return self.new_table(j, i, f_k)

    # Assign guest x_ji to a new table and draw topic (dish) of the table
    def new_table(self, j, i, f_k):
        # search a spare table ID
        T_j = self.n_jt[j].size
        for t_new in range(T_j):
            if t_new not in self.tables[j]: break
        else:
            # new table ID (no spare)
            t_new = T_j
            self.n_jt[j].resize(t_new+1)
            self.n_jt[j][t_new] = 0
            self.k_jt[j].append(0)
        self.tables[j].append(t_new)
        self.n_tables += 1
        self.updated_n_tables()

        # sampling of k for new topic(= dish of new table)
        p_k = [self.m_k[k] * f_k[k] for k in self.topics]
        p_k.append(self.gamma_f_k_new_x_ji)
        k_new = self.sampling_topic(numpy.array(p_k, copy=False))

        self.k_jt[j][t_new] = k_new
        self.m_k[k_new] += 1

        return t_new

    # sampling topic
    # In the case of new topic, allocate resource for parameters
    def sampling_topic(self, p_k):
        drawing = numpy.random.multinomial(1, p_k / p_k.sum()).argmax()
        if drawing < len(self.topics):
            # existing topic
            k_new = self.topics[drawing]
        else:
            # new topic
            K = self.m_k.size
            for k_new in range(K):
                # recycle table ID, if a spare ID exists
                if k_new not in self.topics: break
            else:
                # new table ID, if otherwise
                k_new = K
                self.n_k = numpy.resize(self.n_k, k_new + 1)
                self.n_k[k_new] = 0
                self.m_k = numpy.resize(self.m_k, k_new + 1)
                self.m_k[k_new] = 0
                self.n_kv = numpy.resize(self.n_kv, (k_new+1, self.V))
                self.n_kv[k_new, :] = numpy.zeros(self.V, dtype=int)
            self.topics.append(k_new)
        return k_new

    def sampling_k(self, j, t):
        """sampling k (dish=topic) from posterior"""
        k_old = self.k_jt[j][t]
        n_jt = self.n_jt[j][t]
        self.m_k[k_old] -= 1
        self.n_k[k_old] -= n_jt
        if self.m_k[k_old] == 0:
            self.topics.remove(k_old)

        # sampling of k
        n_jtv = self.count_n_jtv(j, t, k_old)
        K = len(self.topics)
        log_p_k = numpy.zeros(K+1)
        for i, k in enumerate(self.topics):
            log_p_k[i] = self.log_f_k_new_x_jt(n_jt, n_jtv, self.n_kv[k, :], self.n_k[k]) + numpy.log(self.m_k[k])
        log_p_k[K] = self.log_f_k_new_x_jt(n_jt, n_jtv) + numpy.log(self.gamma)
        k_new = self.sampling_topic(numpy.exp(log_p_k - log_p_k.max())) # for too small

        # update counters
        self.k_jt[j][t] = k_new
        self.m_k[k_new] += 1
        self.n_k[k_new] += self.n_jt[j][t]
        for v, t1 in zip(self.x_ji[j], self.t_ji[j]):
            if t1 != t: continue
            self.n_kv[k_new, v] += 1


def hdplda_learning(hdplda, iteration):
    for i in range(iteration):
        hdplda.inference()
        print "-%d K=%d p=%f" % (i + 1, len(hdplda.topics), hdplda.perplexity())
    return hdplda

def main():
    import optparse
    parser = optparse.OptionParser()
    parser.add_option("-f", dest="filename", help="corpus filename")
    parser.add_option("-c", dest="corpus", help="using range of Brown corpus' files(start:end)")
    parser.add_option("--alpha", dest="alpha", type="float", help="parameter alpha", default=numpy.random.gamma(1, 1))
    parser.add_option("--gamma", dest="gamma", type="float", help="parameter gamma", default=numpy.random.gamma(1, 1))
    parser.add_option("--beta", dest="beta", type="float", help="parameter of beta measure H", default=0.5)
    parser.add_option("-k", dest="K", type="int", help="initial number of topics", default=1)
    parser.add_option("-i", dest="iteration", type="int", help="iteration count", default=10)
    parser.add_option("-s", dest="stopwords", type="int", help="0=exclude stop words, 1=include stop words", default=1)
    parser.add_option("--seed", dest="seed", type="int", help="random seed")
    parser.add_option("--df", dest="df", type="int", help="threshold of document freaquency to cut words", default=0)
    (options, args) = parser.parse_args()
    if not (options.filename or options.corpus): parser.error("need corpus filename(-f) or corpus range(-c)")
    if options.seed != None:
        numpy.random.seed(options.seed)

    import vocabulary
    if options.filename:
        corpus = vocabulary.load_file(options.filename)
    else:
        corpus = vocabulary.load_corpus(options.corpus)
        if not corpus: parser.error("corpus range(-c) forms 'start:end'")

    voca = vocabulary.Vocabulary(options.stopwords==0)
    docs = [voca.doc_to_ids(doc) for doc in corpus]
    if options.df > 0: docs = voca.cut_low_freq(docs, options.df)

    hdplda = HDPLDA(options.alpha, options.gamma, options.beta, docs, voca.size())
    print "corpus=%d words=%d alpha=%f gamma=%f beta=%f initK=%d stopwords=%d" % (len(corpus), len(voca.vocas), options.alpha, options.gamma, options.beta, options.K, options.stopwords)
    #hdplda.dump()

    #import cProfile
    #cProfile.runctx('hdplda_learning(hdplda, options.iteration)', globals(), locals(), 'hdplda.profile')
    hdplda_learning(hdplda, options.iteration)

    phi = hdplda.worddist()
    for k, phi_k in enumerate(phi):
        print "\n-- topic: %d" % k
        for w in numpy.argsort(-phi_k)[:20]:
            print "%s: %f" % (voca[w], phi_k[w])

if __name__ == "__main__":
    main()