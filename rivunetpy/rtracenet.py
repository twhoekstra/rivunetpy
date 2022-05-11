import os
from multiprocessing import Pool

import time
import SimpleITK as sitk

from rivunetpy.trace import R2Tracer
from rivunetpy.swc import SWC
from rivunetpy.utils.io import loadswc
from rivunetpy.utils.io import loadimg, crop
from rivunetpy.utils.filtering import apply_threshold
from rivunetpy.trace import estimate_radius
from rivunetpy.utils.segmentation import NeuronSegmentor
from rivunetpy.utils.cells import Neuron

RIVULET_2_TREE_IMG_EXT = '{}rnp{}tif'.format(os.extsep, os.extsep)
RIVULET_2_TREE_SWC_EXT = '{}rnp{}swc'.format(os.extsep, os.extsep)

def check_long_ext(file_to_check, ext):
    return file_to_check.split(os.extsep, 1)[-1] == ext.split(os.extsep, 1)[-1]

def trace_single(neuron, threshold, speed, quality, force_retrace):
    starttime = time.time()
    img = neuron.img
    neuron.swc_fname = '{}{}'.format(neuron.img_fname.split(RIVULET_2_TREE_IMG_EXT)[0], RIVULET_2_TREE_SWC_EXT)

    if os.path.exists(neuron.swc_fname) and not force_retrace:
        swc_mat = loadswc(neuron.swc_fname)
        swc = SWC()
        swc._data = swc_mat
        neuron.add_SWC(swc)
        print(f'Neuron ({neuron.num})\t --Loaded SWC from disk')
    else:
        if threshold in (float, int):
            pass
        elif type(threshold) is str:
            _, reg_thresh = apply_threshold(img, mthd=threshold)
        else:
            _, reg_thresh = apply_threshold(img, mthd='Max Entropy')

        img = sitk.GetArrayFromImage(img)

        img, crop_region = crop(img, reg_thresh)  # Crop by default
        print(f'Neuron ({neuron.num})\t --Tracing neuron of shape {img.shape} '
              f'with a threshold of {reg_thresh}')

        # Run rivulet2 for the first time
        skeletonize = False
        tracer = R2Tracer(quality=quality,
                          silent=True,
                          speed=speed,
                          clean=True,
                          non_stop=False,
                          skeletonize=skeletonize)

        swc, soma = tracer.trace(img, reg_thresh)
        print('Neuron ({})\t -- Finished: {:.2f} sec.'.format(neuron.num, time.time() - starttime))

        # if skeletonized, re-estimate the radius for each node
        if skeletonize:
            print('Re-estimating radius...')
            swc_arr = swc.get_array()
            for i in range(swc_arr.shape[0]):
                swc_arr[i, 5] = estimate_radius(swc_arr[i, 2:5], img > reg_thresh)
            swc._data = swc_arr

        swc.clean()

        swc.apply_soma_TypeID(soma)

        swc.reset(crop_region, 1)

        swc.save(neuron.swc_fname)
        neuron.add_SWC(swc)

    return neuron

def trace_net(file=None, dir_out=None, threshold=None, strict_seg=True, force_recalculate=False,
              speed=False, quality=False, asynchronous=True):

    if threshold is not None and type(threshold) not in (int, float, str):
        raise TypeError('Expected threshold to be either of type str, specifiying an automatic thresholding method \n',
                        f'or a number, specifying the threshold value, instead got {type(threshold)}')

    img_dir, img_name = os.path.split(file)
    img = loadimg(file, 1)

    if dir_out is None:
        dir_out = os.path.splitext(img_name)[0]

    save_dir = os.path.join(img_dir, dir_out)

    if (os.path.exists(save_dir)
            and not force_recalculate
            and any([check_long_ext(fname, RIVULET_2_TREE_IMG_EXT) for fname in os.listdir(save_dir)])):
        neurons = []
        for fname in os.listdir(save_dir):
            if check_long_ext(fname, RIVULET_2_TREE_IMG_EXT):
                loc = os.path.join(save_dir, fname)
                image = loadimg(loc, 1)
                neurons.append(Neuron(image, img_fname=loc, num=len(neurons)))
        print(f'Loaded {len(neurons)} neurons from file.')
    else:
        # Create a new directory next to the input file for the SWC outputs
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)

        neuronsegmentor = NeuronSegmentor(img, strict=strict_seg)
        neuronsegmentor.plot()
        neurons = neuronsegmentor.neurons

        for ii, neuron in enumerate(neurons):
            # Store images
            img_fname = 'neuron_{:04d}{}'.format(ii, RIVULET_2_TREE_IMG_EXT)
            loc = os.path.join(save_dir, img_fname)
            neuron.img_fname = loc
            sitk.WriteImage(neuron.img, neuron.img_fname)
        print(f'Segmented image into {len(neurons)} neurons.')

    result_buffers = []
    with Pool(processes=os.cpu_count() - 1) as pool:

        if asynchronous:
            for neuron in neurons:
                result_buffer = pool.apply_async(trace_single, (neuron, threshold, speed, quality, force_recalculate))
                result_buffers.append(result_buffer)

            results = [result_buffer.get() for result_buffer in result_buffers]
        else:
            for neuron in neurons:
                result_buffers.append(trace_single(neuron, threshold, speed, quality, force_recalculate))

            results = result_buffers