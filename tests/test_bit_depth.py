import os

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from rivuletpy.utils.io import loadswc, loadimg
from rivuletpy.swc import SWC
from skimage.io import imread
from skimage.util import img_as_ubyte
from skimage.filters import threshold_otsu
from skimage import data, restoration, util
import tifffile as tif

from tests import rtrace

FORCE = True

DIR = os.path.join('data', 'test-bitdepth')

FILENAME_uint8 = '8-bit.tif'
FILENAME_uint12 = '12-bit.tif'
FILENAME_uint16 = '16-bit.tif'

SWC_BUFFER_NAME = 'test-bitdepth-buffer.swc'

LABEL = 'downcast'

FONTSIZE = 5


def check_Z(image: Image) -> (int, np.ndarray):
    assert image.ndim == 3, f'Image should have a Z-stack, instead shape is {image.shape}'
    slice_maxes = np.amax(np.reshape(image, (len(image), np.prod(image.shape[1:]))), axis=0)
    return int(np.std(slice_maxes)), slice_maxes

def get_info(images: dict) -> None:
    for bits, image in images.items():
        print(f'\t{bits}-bit:\tImage of TYPE: {image.dtype}\twith '
              f'intensity EXTREMA: {(image.min(), image.max())}\t' 
              f'and intra-layer DEVIATION: {check_Z(image)[0]}')

if __name__ == '__main__':

    image_uint16 = imread(os.path.join(DIR, FILENAME_uint16))
    image_uint12 = imread(os.path.join(DIR, FILENAME_uint12))
    image_uint8 = imread(os.path.join(DIR, FILENAME_uint8))

    images = {8: image_uint8, 12: image_uint12, 16: image_uint16}
    filenames_images = (FILENAME_uint8, FILENAME_uint12, FILENAME_uint16)
    filenames_images = [os.path.join(DIR, filename) for filename in filenames_images]
    get_info(images)

    downcast_images = {}
    downcast_filenames_images = []
    for ii, (bits, image) in enumerate(images.items()):
        downcast_image = (image / (2 ** (bits - 8))).astype(np.uint8)
        downcast_images[bits] = downcast_image
        save_name = os.path.join(DIR, 'downcast_' + filenames_images[ii].replace(DIR + os.sep, ''))
        downcast_filenames_images.append(save_name)
        tif.imwrite(save_name, downcast_image)

    get_info(downcast_images)

    all_images = [images, downcast_images]
    all_filenames = [filenames_images, downcast_filenames_images]
    print(f'(D)\tComplete list of filenames to: {all_filenames}')

    fig, ax = plt.subplots(3, 2*len(images), dpi=300)

    for ii, image_set in enumerate(all_images):
        label = '(Original)' if not ii else '$\\rightarrow$8-bit'
        for jj, (bits, image) in enumerate(image_set.items()):
            kk = jj + ii * len(images)

            image = all_images[ii][bits]
            filename = all_filenames[ii][jj]

            flat_image = np.max(image, axis=0)

            threshold = threshold_otsu(flat_image)

            ax[0, kk].imshow(flat_image, cmap='gray')
            ax[0, kk].set_title(f'{bits}-bit {label}', fontsize=FONTSIZE)
            ax[0, kk].set_axis_off()
            # ax[0, kk].colorbar()
            ax[1, kk].imshow(flat_image > threshold, cmap='gray')
            ax[1, kk].set_title(f'$T={threshold}$', fontsize=FONTSIZE)
            ax[1, kk].set_axis_off()

            swc_name = os.path.join(filename.replace('.tif', '.swc'))

            if (not os.path.exists(swc_name)) or FORCE:
                rtrace.main(file=filename, threshold=threshold, out=SWC_BUFFER_NAME)
                swc_mat = loadswc(SWC_BUFFER_NAME)
                s = SWC()
                s._data = swc_mat
                print(f'(D)\tSaving SWC to: {swc_name}')
                s.save(swc_name)
            else:
                print(f'(D)\tOpening SWC from: {swc_name}')
                swc_mat = loadswc(swc_name)
                s = SWC()
                s._data = swc_mat

            s.as_image(ax=ax[2, kk])
            ax[2, kk].set_title('SWC', fontsize=FONTSIZE)
            ax[2, kk].set_axis_off()

            # print(f'(D)\tSaving plot to: {ff}')
            # fig.savefig(ff)
            # Image.open(ff).convert('RGB').save(ff.replace('.png', '.jpg'), 'JPEG')
            # os.remove(ff)

    fig.show()
    fig.savefig('data/test-bitdepth/test_bit_depth.jpg')

