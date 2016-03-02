###############################################################################
# Deep Dreamer
# Based on https://github.com/google/deepdream/blob/master/dream.ipynb
# Author: Kesara Rathnayake ( kesara [at] kesara [dot] lk )
###############################################################################

import numpy as np
from caffe import Classifier
#from images2gif import writeGif
from scipy.ndimage import affine_transform, zoom
from PIL.Image import fromarray as img_fromarray, open as img_open
import logging
import caffe
logging.basicConfig(filename='log.txt', format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
					level=logging.NOTSET)


def _select_network(netname, toepath):
	if netname == 'bvlc_googlenet':
		NET_FN = toepath+"models/deploy.prototxt"  # Make sure force_backward: true
		PARAM_FN = toepath+"models/bvlc_googlenet.caffemodel"
		CHANNEL_SWAP = (2, 1, 0)
		# ImageNet mean, training set dependent
		CAFFE_MEAN = np.float32([104.0, 116.0, 122.0])
		return NET_FN, PARAM_FN, CHANNEL_SWAP, CAFFE_MEAN
	elif netname == 'googlenet_place205':
		# TODO: refit SWAP and MEAN for places205? These work for now.
		NET_FN = toepath+"models/googlenet_places205/deploy_places205.protxt"  # Make sure force_backward: true
		PARAM_FN = toepath+"models/googlenet_places205/googlelet_places205_train_iter_2400000.caffemodel"
		CHANNEL_SWAP = (2, 1, 0)
		# ImageNet mean, training set dependent
		CAFFE_MEAN = np.float32([104.0, 116.0, 122.0])
		return NET_FN, PARAM_FN, CHANNEL_SWAP, CAFFE_MEAN
	else:
		print("Error: network {} not implemented".format(netname))


def _preprocess(net, img):
	return np.float32(np.rollaxis(img, 2)[::-1]) - net.transformer.mean["data"]


def _deprocess(net, img):
	return np.dstack((img + net.transformer.mean["data"])[::-1])


def _make_step(
		net, step_size=1.5, end="inception_4c/output", jitter=32, clip=True):
	""" Basic gradient ascent step. """

	src = net.blobs["data"]
	dst = net.blobs[end]

	ox, oy = np.random.randint(-jitter, jitter+1, 2)

	# apply jitter shift
	src.data[0] = np.roll(np.roll(src.data[0], ox, -1), oy, -2)

	net.forward(end=end)
	dst.diff[:] = dst.data  # specify the optimization objective
	net.backward(start=end)
	g = src.diff[0]
	# apply normalized ascent step to the input image
	src.data[:] += step_size/np.abs(g).mean() * g
	# unshift image
	src.data[0] = np.roll(np.roll(src.data[0], -ox, -1), -oy, -2)

	if clip:
		bias = net.transformer.mean["data"]
		src.data[:] = np.clip(src.data, -bias, 255-bias)


def _deepdream(
		net, base_img, iter_n=10, octave_n=4, octave_scale=1.4,
		end="inception_4c/output", clip=True, **step_params):
	# prepare base images for all octaves
	octaves = [_preprocess(net, base_img)]

	for i in range(octave_n-1):
		octaves.append(zoom(
			octaves[-1], (1, 1.0/octave_scale, 1.0/octave_scale), order=1))

	src = net.blobs["data"]

	# allocate image for network-produced details
	detail = np.zeros_like(octaves[-1])

	for octave, octave_base in enumerate(octaves[::-1]):
		h, w = octave_base.shape[-2:]
		if octave > 0:
			# upscale details from the previous octave
			h1, w1 = detail.shape[-2:]
			detail = zoom(detail, (1, 1.0*h/h1, 1.0*w/w1), order=1)

		src.reshape(1, 3, h, w)  # resize the network's input image size
		src.data[0] = octave_base+detail

		for i in range(iter_n):
			_make_step(net, end=end, clip=clip, **step_params)

			# visualization
			vis = _deprocess(net, src.data[0])
			if not clip:  # adjust image contrast if clipping is disabled
				vis = vis*(255.0/np.percentile(vis, 99.98))

		# extract details produced on the current octave
		detail = src.data[0]-octave_base

	# returning the resulting image
	return _deprocess(net, src.data[0])


def list_layers(network="bvlc_googlenet"):
	# Load DNN model
	NET_FN, PARAM_FN, CHANNEL_SWAP, CAFFE_MEAN = _select_network(network)
	net = Classifier(
		NET_FN, PARAM_FN, mean=CAFFE_MEAN, channel_swap=CHANNEL_SWAP)
	net.blobs.keys()


def deepdream(
		q, dreamname,toepath, img_path, modegpu=True, gpudevice = 0, zoom=True, scale_coefficient=0.05, irange=5, iter_n=10,
		octave_n=4, octave_scale=1.4, end="inception_4c/output", clip=True,
		network="bvlc_googlenet", gif=False, reverse=False, duration=0.1,
		loop=False):

	if modegpu:
		caffe.set_mode_gpu()
		caffe.set_device(gpudevice)
		print("GPU mode [device id: {}]".format(gpudevice))
		print("using GPU, but you'd still better make a cup of coffee")
	else:
		print("using CPU...")

	img = np.float32(img_open(toepath+"actualframe.jpg"))

	s = scale_coefficient
	h, w = img.shape[:2]

	# Select, load DNN model
	NET_FN, PARAM_FN, CHANNEL_SWAP, CAFFE_MEAN = _select_network(network, toepath)
	net = Classifier(
		NET_FN, PARAM_FN, mean=CAFFE_MEAN, channel_swap=CHANNEL_SWAP)

	img_pool = [img_path,]

	# Save settings used in a log file
	logging.info("{} zoom={}, scale_coefficient={}, irange={}, iter_n={}, octave_n={}, octave_scale={}, end={},"\
			"clip={}, network={}, gif={}, reverse={}, duration={}, loop={}".format(
		img_path, zoom, scale_coefficient, irange, iter_n, octave_n, octave_scale, end, clip, network, gif, reverse,
		duration, loop))

	print("Dreaming...")
	for i in range(irange):
		img = _deepdream(
			net, img, iter_n=iter_n, octave_n=octave_n,
			octave_scale=octave_scale, end=end, clip=clip)
		img_fromarray(np.uint8(img)).save("{}_{}.jpg".format(
			img_path+dreamname, i))
		if gif:
			img_pool.append("{}_{}.jpg".format(img_path, i))
		print("Dream layer depth {} saved.".format(i))
		q.put([i, "{}_{}.jpg".format(img_path, i)])
		#op('moviefileinDream').file = "{}_{}.jpg".format(img_path, i)
		#op('tableDreamshards').appendrow([i,img_path+"_"+i+".jpg"])
		#print("image pool: "+ img_pool)
		print("{}_{}.jpg".format(img_path, i))
		if zoom:
			img = affine_transform(
				img, [1-s, 1-s, 1], [h*s/2, w*s/2, 0], order=1)
	print("Weak up")
	print("��Awake!!")
	if gif:
		frames = None
		if reverse:
			frames = [img_open(f) for f in img_pool[::-1]]
		else:
			frames = [img_open(f) for f in img_pool]
		writeGif(
			"{}.gif".format(img_path), frames, duration=duration,
			repeat=loop)
		print("gif created.")