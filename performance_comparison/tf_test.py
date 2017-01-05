
## Libraries
import pandas as pd
import numpy as np
import tensorflow as tf
from time import time


## Helper functions
def dense_to_one_hot(labels_dense, num_classes=10):
    """Convert class labels from scalars to one-hot vectors"""
    num_samples = labels_dense.shape[0]
    index_offset = np.arange(num_samples) * num_classes
    labels_one_hot = np.zeros((num_samples, num_classes))
    labels_one_hot.flat[index_offset + labels_dense.ravel()] = 1
    
    return labels_one_hot


## Set all variables
# number of neurons, patch size, number of feature map
num_channels = 1
image_size = 28
hidden1_num_units = 128
hidden2_num_units = 128
label_units = 10
patch_size = 3
fmap = [16, 32]
drop_ratio = [1., 1., 1.]

# set remaining variables
batch_size = 32
learning_rate = 0.05
lmbda = 0.005


## Read data from CSV file
print "Initializing..."
train = pd.read_csv("./convnet_MNIST/train.csv").values
train, train_label = train[:,1:]/255., train[:,0]
split_size = 20000 #int(train.shape[0]*0.85)
train_x, val_x = train[:split_size, :], train[split_size:split_size+5000, :]
train_x, val_x = train_x.reshape(-1, image_size, image_size, num_channels), val_x.reshape(-1, image_size, image_size, num_channels)
train_y, val_y = train_label[:split_size].reshape(-1,1), train_label[split_size:split_size+5000].reshape(-1,1)
train_y, val_y = dense_to_one_hot(train_y), dense_to_one_hot(val_y)
del train, train_label


## Define weights and biases of the neural network
weights = {
    'conv1': tf.Variable(tf.random_normal([5, 5, 1, fmap[0]], stddev=0.05)),
    'conv2': tf.Variable(tf.random_normal([5, 5, fmap[0], fmap[1]], stddev=0.05)),
    'hidden1': tf.Variable(tf.truncated_normal(
        [fmap[1]*4*4, hidden1_num_units],
        stddev=2.0 / np.sqrt(float(fmap[1]*4*4)))),
    'hidden2': tf.Variable(tf.truncated_normal(
        [hidden1_num_units, hidden2_num_units],
        stddev=2.0 / np.sqrt(float(hidden1_num_units)))),
    'output': tf.Variable(tf.truncated_normal([hidden2_num_units, label_units],
        stddev=2.0 / np.sqrt(float(hidden2_num_units))))
}
biases = {
    'conv1': tf.Variable(tf.zeros([fmap[0]])),
    'conv2': tf.Variable(tf.zeros([fmap[1]])),
    'hidden1': tf.Variable(tf.zeros([hidden1_num_units])),
    'hidden2': tf.Variable(tf.zeros([hidden2_num_units])),
    'output': tf.Variable(tf.zeros([label_units]))
}
def feedforward(data, weights, biases, drop_param):
    data_size = tf.shape(data)[0]
    conv = tf.nn.conv2d(data, weights['conv1'], [1,1,1,1], padding='VALID')
    hidden = tf.nn.relu(conv + biases['conv1'])
    pool = tf.nn.max_pool(hidden, [1, 2, 2, 1], [1, 2, 2, 1], padding='VALID')
    conv = tf.nn.conv2d(pool, weights['conv2'], [1,1,1,1], padding='VALID')
    hidden = tf.nn.relu(conv + biases['conv2'])
    pool = tf.nn.max_pool(hidden, [1, 2, 2, 1], [1, 2, 2, 1], padding='VALID')
    flat = tf.reshape(pool, [data_size, -1])
    flat = tf.nn.dropout(flat, drop_param[0])
    hidden = tf.nn.relu(tf.matmul(flat, weights['hidden1']) + biases['hidden1'])
    hidden = tf.nn.dropout(hidden, drop_param[1])
    hidden = tf.nn.relu(tf.matmul(hidden, weights['hidden2']) + biases['hidden2'])
    hidden = tf.nn.dropout(hidden, drop_param[2])
    logits = tf.matmul(hidden, weights['output']) + biases['output']
    return logits

## Define placeholders
x = tf.placeholder(tf.float32, [None, image_size, image_size, num_channels])
y = tf.placeholder(tf.float32, [None, label_units])
drop_param = tf.placeholder(tf.float32, [3,])

## Construct tensor flow
logits = feedforward(x, weights, biases, drop_param)
l2_norm_squared = sum([tf.nn.l2_loss(weights[layer]) for layer in weights])
cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits, y)) + \
        tf.div(lmbda*l2_norm_squared, tf.to_float(tf.shape(x)[0]))
optimizer = tf.train.AdamOptimizer(learning_rate=0.001).minimize(cost)
#optimizer = tf.train.GradientDescentOptimizer(learning_rate=learning_rate).minimize(cost)
pred = tf.argmax(tf.nn.softmax(feedforward(x, weights, biases, drop_param)), 1)
accu = tf.reduce_mean(tf.cast( tf.equal(pred, tf.argmax(y, 1)), tf.float32 ))

## Start training!
epochs = 15
num_batches = train_x.shape[0]/batch_size
init = tf.initialize_all_variables()
best_val_cost = 10

with tf.Session() as sess:
    """
    for each epoch, do:
        for each batch, do:
            create pre-processed batch
            run optimizer by feeding batch
            find cost and reiterate to minimize
    """
    sess.run(init)
    print('Initialized. Start training...')
    t0 = time()
    for epoch in xrange(epochs):
        avg_cost = 0
        for step in xrange(num_batches):
            #batch_mask = np.random.choice(np.arange(train_x.shape[0]), batch_size, replace=False)
            #batch_x, batch_y = train_x[[batch_mask]], train_y[[batch_mask]]
            offset = step * batch_size
            batch_x, batch_y = train_x[offset:(offset+batch_size), :], train_y[offset:(offset+batch_size), :]
            _, c = sess.run([optimizer, cost], feed_dict={x: batch_x, y: batch_y, drop_param: drop_ratio})
            avg_cost += (c / num_batches)

        print "Epoch:", (epoch+1), "\n  avg minibatch cost = {:.5f}".format(avg_cost)
        batch_accu = accu.eval({x: batch_x, y: batch_y, drop_param: [1, 1, 1]})
        print "  minibatch accuracy: {:.2%}".format(batch_accu)
        val_cost = cost.eval({x: val_x, y: val_y, drop_param: [1, 1, 1]})
        print "  validation cost = {:.5f}".format(val_cost)
        val_accu = accu.eval({x: val_x, y: val_y, drop_param: [1, 1, 1]})
        print "  validation accuracy: {:.2%}".format(val_accu)
        if val_cost <= best_val_cost:
            best_val_cost = val_cost
            print "This is the best model to date."
            
        # shuffle the data
        order = np.arange(train_x.shape[0])
        np.random.shuffle(order)
        train_x = train_x[order]
        train_y = train_y[order]

    print "\nTraining complete!"
    print "\nElapsed time:", time()-t0

    

