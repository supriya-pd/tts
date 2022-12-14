

from __future__ import print_function

from hyperparams import Hyperparams as hp
import numpy as np
import tensorflow as tf
from utils import *
import codecs
import re
import os
import unicodedata

def load_vocab():
    char2idx = {char: idx for idx, char in enumerate(hp.vocab)}
    idx2char = {idx: char for idx, char in enumerate(hp.vocab)}
    return char2idx, idx2char

def text_normalize(text):
    text = ''.join(char for char in unicodedata.normalize('NFD', text)
                           if unicodedata.category(char) != 'Mn') # Strip accents

    text = text.lower()
    text = re.sub("[^{}]".format(hp.vocab), " ", text)
    text = re.sub("[ ]+", " ", text)
    return text

def load_data(mode="train"):
    # Load vocabulary
    char2idx, idx2char = load_vocab()

    if mode in ("train", "eval"):
        # Parse
        fpaths, text_lengths, texts = [], [], []
        transcript = os.path.join(hp.data, 'transcript.csv')
        lines = codecs.open(transcript, 'r', 'utf-8').readlines()
        total_hours = 0
        if mode=="train":
            lines = lines[1:]
        else: 
            lines = lines[:1]

        for line in lines:
            fname, _, text = line.strip().split("|")

            fpath = os.path.join(hp.data, "wavs", fname + ".wav")
            fpaths.append(fpath)

            text = text_normalize(text) + "E"  # E: EOS
            text = [char2idx[char] for char in text]
            text_lengths.append(len(text))
            texts.append(np.array(text, np.int32).tostring())

        return fpaths, text_lengths, texts
    else:
        # Parse
        lines = codecs.open(hp.test_data, 'r', 'utf-8').readlines()[1:]
        sents = [text_normalize(line.split(" ", 1)[-1]).strip() + "E" for line in lines] # text normalization, E: EOS
        lengths = [len(sent) for sent in sents]
        maxlen = sorted(lengths, reverse=True)[0]
        texts = np.zeros((len(sents), maxlen), np.int32)
        for i, sent in enumerate(sents):
            texts[i, :len(sent)] = [char2idx[char] for char in sent]
        return texts

def get_batch():
    """Loads training data and put them in queues"""
    with tf.device('/cpu:0'):
        # Load data
        fpaths, text_lengths, texts = load_data() # list
        maxlen, minlen = max(text_lengths), min(text_lengths)

        # Calc total batch count
        num_batch = len(fpaths) // hp.batch_size

        fpaths =  tf.convert_to_tensor(fpaths)
        text_lengths =  tf.convert_to_tensor(text_lengths)
        texts =  tf.convert_to_tensor(texts)

        # Create Queues
        
       ## num_epochs=10
        fpath, text_length, text = tf.compat.v1.train.slice_input_producer([fpaths, text_lengths, texts], shuffle=True)
        # fpath=tf.data.Dataset.from_tensor_slices(fpaths).shuffle(tf.shape(fpaths, out_type=tf.int64)[0]).repeat(num_epochs)
        # text_length=tf.data.Dataset.from_tensor_slices(text_lengths).shuffle(tf.shape(text_lengths, out_type=tf.int64)[0]).repeat(num_epochs)
        # text=tf.data.Dataset.from_tensor_slices(texts).shuffle(tf.shape(texts, out_type=tf.int64)[0]).repeat(num_epochs)
        #print(type(text))
        #text=np.stack(list(text))
        # Parse
        
        text = tf.decode_raw(text, tf.int32)  # (None,)

        if hp.prepro:
            def _load_spectrograms(fpath):
                fname = os.path.basename(fpath)
                mel = "mels/{}".format(fname.decode("utf-8").replace("wav", "npy"))
                mag = "mags/{}".format(fname.decode("utf-8").replace("wav", "npy"))
                return fname, np.load(mel), np.load(mag)

            fname, mel, mag = tf.py_func(_load_spectrograms, [fpath], [tf.string, tf.float32, tf.float32])
        else:
            fname, mel, mag = tf.py_func(load_spectrograms, [fpath], [tf.string, tf.float32, tf.float32])  # (None, n_mels)

        # Add shape information
        fname.set_shape(())
        text.set_shape((None,))
        mel.set_shape((None, hp.n_mels*hp.r))
        mag.set_shape((None, hp.n_fft//2+1))

        # Batching
        _, (texts, mels, mags, fnames) = tf.contrib.training.bucket_by_sequence_length(
                                            input_length=text_length,
                                            tensors=[text, mel, mag, fname],
                                            batch_size=hp.batch_size,
                                            bucket_boundaries=[i for i in range(minlen + 1, maxlen - 1, 20)],
                                            num_threads=16,
                                            capacity=hp.batch_size * 4,
                                            dynamic_pad=True)

    return texts, mels, mags, fnames, num_batch

