"""convnet.py
~~~~~~~~~~~~~~

A Theano-based program for training and running simple neural
networks.

Supports several layer types (fully connected, convolutional, max
pooling, softmax), and activation functions (sigmoid, tanh, and
rectified linear units, with more easily added).

This program is revised from Michael Nielsen's ebook 
Neural Networks and Deep Learning (http://neuralnetworksanddeeplearning.com),
incorporating ideas from the Theano documentation on convolutional neural nets (notably,
http://deeplearning.net/tutorial/lenet.html), from Misha Denil's
implementation of dropout (https://github.com/mdenil/dropout), and
from Chris Olah (http://colah.github.io).

"""

#### Libraries
# Standard library
import six.moves.cPickle as pickle
import gzip

# Third-party libraries
import numpy as np
import scipy
import theano
import theano.tensor as T
from theano.tensor.nnet import conv2d
from theano.tensor.nnet import softmax
from theano.tensor import shared_randomstreams
from theano.tensor.signal import pool

# Activation functions for neurons
def linear(z): return z
def ReLU(z): return T.maximum(0.0, z)
from theano.tensor.nnet import sigmoid
from theano.tensor import tanh


#### Constants
GPU = False
if GPU:
    print "Trying to run under a GPU.  If this is not desired, then modify "+\
        "the GPU flag to False."
    try: theano.config.device = 'gpu'
    except: pass # it's already set
    theano.config.floatX = 'float32'
else:
    print "Running with a CPU.  If this is not desired, then the modify "+\
        "the GPU flag to True."


#### Main class used to construct and train networks

class Network(object):

    def __init__(self, layers):
        """Takes a list of `layers`, describing the network architecture, and
        a value for the `mini_batch_size` to be used during training
        by stochastic gradient descent.

        """
        self.layers = layers
        self.params = [param for layer in self.layers for param in layer.params]


    def feedforward(self, mini_batch_size):
        self.x = T.matrix("x")  # data, presented as rasterized images
        self.y = T.ivector("y")  # labels, presented as 1D vector of [int] labels
        init_layer = self.layers[0]
        init_layer.set_inpt(self.x, self.x, mini_batch_size)
        for j in xrange(1, len(self.layers)):
            prev_layer, layer = self.layers[j-1], self.layers[j]
            layer.set_inpt(
                prev_layer.output, prev_layer.output_dropout, mini_batch_size)


    def fit(self, train_data, epochs, mini_batch_size, eta,
            valid_data, test_data=None, lmbda=0.0, early_stop=False, optim_mode='gd'):
        """Train the network using mini-batch stochastic gradient descent."""
        train_x, train_y = train_data
        valid_x, valid_y = valid_data
        if test_data:
            test_x, test_y = test_data

        ## Compute number of minibatches for training, validation and testing
        dataSize = size(train_data)
        num_train_batches = dataSize/mini_batch_size
        num_valid_batches = size(valid_data)/mini_batch_size
        if test_data:
            num_test_batches = size(test_data)/mini_batch_size

        ## Set the (regularized) cost function, symbolic gradients, and updates
        self.feedforward(mini_batch_size)
        l2_norm_squared = sum([(layer.w**2).sum() for layer in self.layers])
        cost = self.layers[-1].cost(self)+\
               0.5*lmbda*l2_norm_squared/mini_batch_size
        if optim_mode=='gd':
            grads = T.grad(cost, self.params)
            updates = [(param, param-eta*grad)
                        for param, grad in zip(self.params, grads)]
        if optim_mode=='adam':
            updates = Adam(cost, self.params)

        ## Set functions to train a mini-batch, and to compute the
        ## accuracy in validation and test mini-batches.
        i = T.lscalar() # mini-batch index
        train_mb = theano.function(
            [i], cost, updates=updates,
            givens={
                self.x:
                train_x[i*mini_batch_size: (i+1)*mini_batch_size],
                self.y:
                train_y[i*mini_batch_size: (i+1)*mini_batch_size]
            })
        validate_mb_accuracy = theano.function(
            [i], self.layers[-1].accuracy(self.y),
            givens={
                self.x:
                valid_x[i*mini_batch_size: (i+1)*mini_batch_size],
                self.y:
                valid_y[i*mini_batch_size: (i+1)*mini_batch_size]
            })
        if test_data:
            test_mb_accuracy = theano.function(
                [i], self.layers[-1].accuracy(self.y),
                givens={
                    self.x:
                    test_x[i*mini_batch_size: (i+1)*mini_batch_size],
                    self.y:
                    test_y[i*mini_batch_size: (i+1)*mini_batch_size]
                })
        orderMask = T.ivector()
        shuffleData = theano.function([orderMask], None, updates=[(train_x, train_x[orderMask])])
        shuffleLabel = theano.function([orderMask], None, updates=[(train_y, train_y[orderMask])])            

        ## Train the model
        print("\nStart training......\n")
        # Early-stopping parameters
        patience = 10000           # look as this many examples regardless
        patience_increase = 2      # wait this much longer when a new best is found
        improve_threshold = 1.001  # a relative improvement of this much is
                                   # considered significant
        
        best_valid_accuracy = 0.0
        done_looping = False
        epoch = 0
        while (epoch < epochs) and (not done_looping):
            epoch = epoch + 1
            for minibatch_index in xrange(num_train_batches):
                iter = num_train_batches*(epoch-1) + minibatch_index + 1
                if iter % 1000 == 0:
                    print("Training mini-batch number {0}".format(iter))
                cost_ij = train_mb(minibatch_index)
                if iter % num_train_batches == 0:
                    valid_accuracy = np.mean(
                        [validate_mb_accuracy(j) for j in xrange(num_valid_batches)])
                    print("Epoch {0}: validation accuracy {1:.2%}".format(
                        epoch, valid_accuracy))
                    if valid_accuracy >= best_valid_accuracy:
                        if valid_accuracy >= (best_valid_accuracy * \
                            improve_threshold) and early_stop:
                            patience = max(patience, iter * patience_increase)
                        print("This is the best validation accuracy to date.")
                        best_valid_accuracy = valid_accuracy
                        best_iter = iter
                        if test_data:
                            test_accuracy = np.mean(
                                [test_mb_accuracy(j) for j in xrange(num_test_batches)])
                            print('The corresponding test accuracy is {0:.2%}'.format(
                                test_accuracy))
                        # save the best model
                        with open('best_model.pkl', 'wb') as f:
                            pickle.dump(self, f)
                        
                if early_stop and patience <= iter:
                    done_looping = True
                    break
            # shuffle the data
            order = np.random.permutation(np.arange(dataSize, dtype=np.int32))
            shuffleData(order)
            shuffleLabel(order)
        
        print("Finished training network.")
        print("Best validation accuracy of {0:.2%} obtained at iteration {1}".format(
            best_valid_accuracy, best_iter))

    
    def predict(self, test_data):
        """Output the predicted values from trained model (the net). The
        data input is a theano shared variable array.

        """
        self.feedforward(test_data.get_value().shape[0])
        prediction = theano.function(
            inputs=[],
            outputs=self.layers[-1].y_out,
            givens={self.x: test_data})
        return prediction()



#### Define layer types

class ConvPoolLayer(object):
    """Used to create a combination of a convolutional and a max-pooling
    layer.  A more sophisticated implementation would separate the
    two, but for our purposes we'll always use them together, and it
    simplifies the code, so it makes sense to combine them.

    """

    def __init__(self, filter_shape, image_shape, poolsize=(2, 2),
                 activation_fn=sigmoid, init='trunc_normal'):
        """`filter_shape` is a tuple of length 4, whose entries are the number
        of filters, the number of input feature maps, the filter height, and the
        filter width.

        `image_shape` is a tuple of length 4, whose entries are the
        mini-batch size, the number of input feature maps, the image
        height, and the image width.

        `poolsize` is a tuple of length 2, whose entries are the y and
        x pooling sizes.

        """
        self.filter_shape = filter_shape
        self.image_shape = image_shape
        self.poolsize = poolsize
        self.activation_fn = activation_fn
        # initialize weights and biases
        fan_in = filter_shape[1] * np.prod(filter_shape[2:])
        fan_out = filter_shape[0] * np.prod(filter_shape[2:])
        if init=='glorot_uniform':
            self.w = theano.shared(
                np.asarray(
                    np.random.uniform(-0.15, 0.15, size=filter_shape),
                    dtype=theano.config.floatX),
                borrow=True)
        if init=='trunc_normal':
            self.w = theano.shared(
                np.asarray(
                    scipy.stats.truncnorm.rvs(-2, 2, loc=0, scale=0.1, size=filter_shape),
                    dtype=theano.config.floatX),
                borrow=True)
        if init=='normal':
            self.w = theano.shared(
                np.asarray(
                    np.random.normal(
                        loc=0.0, scale=0.05, size=filter_shape),
                    dtype=theano.config.floatX),
                borrow=True)
        self.b = theano.shared(
            np.asarray(
                np.zeros((filter_shape[0],)),
                dtype=theano.config.floatX),
            borrow=True)
        self.params = [self.w, self.b]

    def set_inpt(self, inpt, inpt_dropout, mini_batch_size):
        shape = tuple([mini_batch_size] + list(self.image_shape))
        self.inpt = inpt.reshape(shape)
        conv_out = conv2d(
            input=self.inpt, filters=self.w, filter_shape=self.filter_shape,
            input_shape=shape)
        pooled_out = pool.pool_2d(
            input=conv_out, ds=self.poolsize, ignore_border=True, mode='max')
        self.output = self.activation_fn(
            pooled_out + self.b.dimshuffle('x', 0, 'x', 'x'))
        self.output_dropout = self.output # no dropout in the convolutional layers

class FullyConnectedLayer(object):

    def __init__(self, n_in, n_out, activation_fn=sigmoid, p_dropout=0.0):
        self.n_in = n_in
        self.n_out = n_out
        self.activation_fn = activation_fn
        self.p_dropout = p_dropout
        # Initialize weights and biases
        self.w = theano.shared(
            np.asarray(
                np.random.normal(
                    loc=0.0, scale=np.sqrt(2.0/n_in), size=(n_in, n_out)),
                dtype=theano.config.floatX),
            name='w', borrow=True)
        self.b = theano.shared(
            np.zeros((n_out,), dtype=theano.config.floatX),
            name='b', borrow=True)
        self.params = [self.w, self.b]

    def set_inpt(self, inpt, inpt_dropout, mini_batch_size):
        self.inpt = inpt.reshape((mini_batch_size, self.n_in))
        self.output = self.activation_fn(
            (1-self.p_dropout)*T.dot(self.inpt, self.w) + self.b)
        self.y_out = T.argmax(self.output, axis=1)
        self.inpt_dropout = dropout_layer(
            inpt_dropout.reshape((mini_batch_size, self.n_in)), self.p_dropout)
        self.output_dropout = self.activation_fn(
            T.dot(self.inpt_dropout, self.w) + self.b)

    def accuracy(self, y):
        "Return the accuracy for the mini-batch."
        return T.mean(T.eq(y, self.y_out))

class SoftmaxLayer(object):

    def __init__(self, n_in, n_out, p_dropout=0.0):
        self.n_in = n_in
        self.n_out = n_out
        self.p_dropout = p_dropout
        # Initialize weights and biases
        self.w = theano.shared(
            np.zeros((n_in, n_out), dtype=theano.config.floatX),
            name='w', borrow=True)
        self.b = theano.shared(
            np.zeros((n_out,), dtype=theano.config.floatX),
            name='b', borrow=True)
        self.params = [self.w, self.b]

    def set_inpt(self, inpt, inpt_dropout, mini_batch_size):
        self.inpt = inpt.reshape((mini_batch_size, self.n_in))
        self.output = softmax((1-self.p_dropout)*T.dot(self.inpt, self.w) + self.b)
        self.y_out = T.argmax(self.output, axis=1)
        self.inpt_dropout = dropout_layer(
            inpt_dropout.reshape((mini_batch_size, self.n_in)), self.p_dropout)
        self.output_dropout = softmax(T.dot(self.inpt_dropout, self.w) + self.b)

    def cost(self, net):
        "Return the log-likelihood cost."
        return -T.mean(T.log(self.output_dropout)[T.arange(net.y.shape[0]), net.y])

    def accuracy(self, y):
        "Return the accuracy for the mini-batch."
        return T.mean(T.eq(y, self.y_out))


#### Helper functions
def size(data):
    "Return the number of samples of the dataset `data`."
    return data[0].get_value(borrow=True).shape[0]

def dropout_layer(layer, p_dropout):
    srng = shared_randomstreams.RandomStreams(
        np.random.RandomState(0).randint(999999))
    mask = srng.binomial(n=1, p=1-p_dropout, size=layer.shape)
    return layer*T.cast(mask, theano.config.floatX)

def Adam(cost, params, lr=0.001, beta1=0.9, beta2=0.999, e=1e-8):
    # see the paper https://arxiv.org/abs/1412.6980
    updates = []
    grads = T.grad(cost, params)
    t = theano.shared(np.float32(1))
    lr_t = lr * T.sqrt(1 - beta2**t)/(1 - beta1**t)
    e_hat = e * T.sqrt(1 - beta2**t)
    for param, grad in zip(params, grads):
        m = theano.shared(np.zeros(param.get_value().shape, dtype=theano.config.floatX))
        v = theano.shared(np.zeros(param.get_value().shape, dtype=theano.config.floatX))
        m_t = ((1 - beta1) * grad) + (beta1 * m)  # Update biased first moment estimate
        v_t = ((1 - beta2) * T.sqr(grad)) + (beta2 * v)  # Update biased second raw moment estimate
        #m_hat = m_t / (1 - beta1**t)  # Compute bias-corrected first moment estimate
        #v_hat = v_t / (1 - beta2**t)  # Compute bias-corrected second raw moment estimate
        grad_t = m_t / (T.sqrt(v_t) + e_hat)
        param_t = param - (lr_t * grad_t)  # Update parameters
        updates.append((m, m_t))
        updates.append((v, v_t))
        updates.append((param, param_t))
    updates.append((t, t+1))
    return updates
