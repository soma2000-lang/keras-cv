# Copyright 2023 The KerasCV Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import time
import unittest

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from tensorflow import keras

from keras_cv import bounding_box
from keras_cv.backend import random
from keras_cv.layers import RandomFlip
from keras_cv.layers.preprocessing.base_image_augmentation_layer import (
    BaseImageAugmentationLayer,
)
from keras_cv.layers.preprocessing.vectorized_base_image_augmentation_layer import (  # noqa: E501
    BOUNDING_BOXES,
)
from keras_cv.layers.preprocessing.vectorized_base_image_augmentation_layer import (  # noqa: E501
    IMAGES,
)

# In order to support both unbatched and batched inputs, the horizontal
# and vertical axis is reverse indexed
H_AXIS = -3
W_AXIS = -2

# Defining modes for random flipping
HORIZONTAL = "horizontal"
VERTICAL = "vertical"
HORIZONTAL_AND_VERTICAL = "horizontal_and_vertical"


class OldRandomFlip(BaseImageAugmentationLayer):
    """A preprocessing layer which randomly flips images.

    This layer will flip the images horizontally and or vertically based on the
    `mode` attribute.

    Input shape:
      3D (unbatched) or 4D (batched) tensor with shape:
      `(..., height, width, channels)`, in `"channels_last"` format.

    Output shape:
      3D (unbatched) or 4D (batched) tensor with shape:
      `(..., height, width, channels)`, in `"channels_last"` format.

    Arguments:
      mode: String indicating which flip mode to use. Can be `"horizontal"`,
        `"vertical"`, or `"horizontal_and_vertical"`, defaults to
        `"horizontal"`. `"horizontal"` is a left-right flip and `"vertical"` is
        a top-bottom flip.
      seed: Integer. Used to create a random seed.
      bounding_box_format: The format of bounding boxes of input dataset.
        Refer to
        https://github.com/keras-team/keras-cv/blob/master/keras_cv/bounding_box/converters.py
        for more details on supported bounding box formats.
    """

    def __init__(
        self, mode=HORIZONTAL, seed=None, bounding_box_format=None, **kwargs
    ):
        super().__init__(seed=seed, force_generator=True, **kwargs)
        self.mode = mode
        self.seed = seed
        if mode == HORIZONTAL:
            self.horizontal = True
            self.vertical = False
        elif mode == VERTICAL:
            self.horizontal = False
            self.vertical = True
        elif mode == HORIZONTAL_AND_VERTICAL:
            self.horizontal = True
            self.vertical = True
        else:
            raise ValueError(
                "RandomFlip layer {name} received an unknown mode="
                "{arg}".format(name=self.name, arg=mode)
            )
        self.auto_vectorize = True
        self.bounding_box_format = bounding_box_format

    def augment_label(self, label, transformation, **kwargs):
        return label

    def augment_image(self, image, transformation, **kwargs):
        return OldRandomFlip._flip_image(image, transformation)

    def get_random_transformation(self, **kwargs):
        flip_horizontal = False
        flip_vertical = False
        if self.horizontal:
            flip_horizontal = (
                random.uniform(shape=[], seed=self._seed_generator) > 0.5
            )
        if self.vertical:
            flip_vertical = (
                random.uniform(shape=[], seed=self._seed_generator) > 0.5
            )
        return {
            "flip_horizontal": tf.cast(flip_horizontal, dtype=tf.bool),
            "flip_vertical": tf.cast(flip_vertical, dtype=tf.bool),
        }

    def _flip_image(image, transformation):
        flipped_output = tf.cond(
            transformation["flip_horizontal"],
            lambda: tf.image.flip_left_right(image),
            lambda: image,
        )
        flipped_output = tf.cond(
            transformation["flip_vertical"],
            lambda: tf.image.flip_up_down(flipped_output),
            lambda: flipped_output,
        )
        flipped_output.set_shape(image.shape)
        return flipped_output

    def _flip_bounding_boxes_horizontal(bounding_boxes):
        x1, x2, x3, x4 = tf.split(
            bounding_boxes["boxes"], [1, 1, 1, 1], axis=-1
        )
        output = tf.stack(
            [
                1 - x3,
                x2,
                1 - x1,
                x4,
            ],
            axis=-1,
        )
        bounding_boxes = bounding_boxes.copy()
        bounding_boxes["boxes"] = tf.squeeze(output, axis=1)
        return bounding_boxes

    def _flip_bounding_boxes_vertical(bounding_boxes):
        x1, x2, x3, x4 = tf.split(
            bounding_boxes["boxes"], [1, 1, 1, 1], axis=-1
        )
        output = tf.stack(
            [
                x1,
                1 - x4,
                x3,
                1 - x2,
            ],
            axis=-1,
        )
        output = tf.squeeze(output, axis=1)
        bounding_boxes = bounding_boxes.copy()
        bounding_boxes["boxes"] = output
        return bounding_boxes

    def augment_bounding_boxes(
        self, bounding_boxes, transformation=None, image=None, **kwargs
    ):
        if self.bounding_box_format is None:
            raise ValueError(
                "`RandomFlip()` was called with bounding boxes,"
                "but no `bounding_box_format` was specified in the constructor."
                "Please specify a bounding box format in the constructor. i.e."
                "`RandomFlip(bounding_box_format='xyxy')`"
            )
        bounding_boxes = bounding_boxes.copy()
        bounding_boxes = bounding_box.convert_format(
            bounding_boxes,
            source=self.bounding_box_format,
            target="rel_xyxy",
            images=image,
        )
        bounding_boxes = tf.cond(
            transformation["flip_horizontal"],
            lambda: OldRandomFlip._flip_bounding_boxes_horizontal(
                bounding_boxes
            ),
            lambda: bounding_boxes,
        )
        bounding_boxes = tf.cond(
            transformation["flip_vertical"],
            lambda: OldRandomFlip._flip_bounding_boxes_vertical(bounding_boxes),
            lambda: bounding_boxes,
        )
        bounding_boxes = bounding_box.clip_to_image(
            bounding_boxes,
            bounding_box_format="rel_xyxy",
            images=image,
        )
        bounding_boxes = bounding_box.convert_format(
            bounding_boxes,
            source="rel_xyxy",
            target=self.bounding_box_format,
            dtype=self.compute_dtype,
            images=image,
        )
        return bounding_box.to_ragged(bounding_boxes)

    def augment_segmentation_mask(
        self, segmentation_mask, transformation=None, **kwargs
    ):
        return OldRandomFlip._flip_image(segmentation_mask, transformation)

    def compute_output_shape(self, input_shape):
        return input_shape

    def get_config(self):
        config = {
            "mode": self.mode,
            "seed": self.seed,
            "bounding_box_format": self.bounding_box_format,
        }
        base_config = super().get_config()
        return dict(list(base_config.items()) + list(config.items()))


class RandomFlipTest(tf.test.TestCase):
    def test_consistency_with_old_impl(self):
        mode = HORIZONTAL_AND_VERTICAL
        image = tf.random.uniform(shape=(1, 64, 64, 3)) * 255.0

        layer = RandomFlip(
            mode=mode,
        )
        old_layer = OldRandomFlip(
            mode=mode,
        )

        with unittest.mock.patch.object(
            random,
            "uniform",
            return_value=tf.convert_to_tensor([[0.6]]),
        ):
            output = layer(image)
        with unittest.mock.patch.object(
            random,
            "uniform",
            return_value=tf.convert_to_tensor(0.6),
        ):
            old_output = old_layer(image)

        self.assertAllClose(old_output, output)


if __name__ == "__main__":
    # Run benchmark
    (x_train, _), _ = keras.datasets.cifar10.load_data()
    x_train = x_train.astype(np.float32)

    is_inputs_containing_bounding_boxes = False
    num_images = [100, 200, 500, 1000]
    results = {}
    aug_candidates = [RandomFlip, OldRandomFlip]
    aug_args = {
        "mode": HORIZONTAL_AND_VERTICAL,
        "bounding_box_format": "xyxy",
    }

    for aug in aug_candidates:
        # Eager Mode
        c = aug.__name__
        layer = aug(**aug_args)
        runtimes = []
        print(f"Timing {c}")

        for n_images in num_images:
            inputs = {IMAGES: x_train[:n_images]}
            if is_inputs_containing_bounding_boxes:
                inputs.update(
                    {
                        BOUNDING_BOXES: {
                            "classes": tf.zeros(shape=(n_images, 4)),
                            "boxes": tf.zeros(shape=(n_images, 4, 4)),
                        }
                    }
                )
            # warmup
            layer(inputs)

            t0 = time.time()
            r1 = layer(inputs)
            t1 = time.time()
            runtimes.append(t1 - t0)
            print(f"Runtime for {c}, n_images={n_images}: {t1-t0}")
        results[c] = runtimes

        # Graph Mode
        c = aug.__name__ + " Graph Mode"
        layer = aug(**aug_args)

        @tf.function()
        def apply_aug(inputs):
            return layer(inputs)

        runtimes = []
        print(f"Timing {c}")

        for n_images in num_images:
            inputs = {IMAGES: x_train[:n_images]}
            if is_inputs_containing_bounding_boxes:
                inputs.update(
                    {
                        BOUNDING_BOXES: {
                            "classes": tf.zeros(shape=(n_images, 4)),
                            "boxes": tf.zeros(shape=(n_images, 4, 4)),
                        }
                    }
                )
            # warmup
            apply_aug(inputs)

            t0 = time.time()
            r1 = apply_aug(inputs)
            t1 = time.time()
            runtimes.append(t1 - t0)
            print(f"Runtime for {c}, n_images={n_images}: {t1-t0}")
        results[c] = runtimes

        # XLA Mode
        # OldRandomFlip fails to run on XLA
        if aug is OldRandomFlip:
            continue
        c = aug.__name__ + " XLA Mode"
        layer = aug(**aug_args)

        @tf.function(jit_compile=True)
        def apply_aug(inputs):
            return layer(inputs)

        runtimes = []
        print(f"Timing {c}")

        for n_images in num_images:
            inputs = {IMAGES: x_train[:n_images]}
            if is_inputs_containing_bounding_boxes:
                inputs.update(
                    {
                        BOUNDING_BOXES: {
                            "classes": tf.zeros(shape=(n_images, 4)),
                            "boxes": tf.zeros(shape=(n_images, 4, 4)),
                        }
                    }
                )
            # warmup
            apply_aug(inputs)

            t0 = time.time()
            r1 = apply_aug(inputs)
            t1 = time.time()
            runtimes.append(t1 - t0)
            print(f"Runtime for {c}, n_images={n_images}: {t1-t0}")
        results[c] = runtimes

    plt.figure()
    for key in results:
        plt.plot(num_images, results[key], label=key)
        plt.xlabel("Number images")

    plt.ylabel("Runtime (seconds)")
    plt.legend()
    plt.savefig("comparison.png")

    # So we can actually see more relevant margins
    del results[aug_candidates[1].__name__]
    plt.figure()
    for key in results:
        plt.plot(num_images, results[key], label=key)
        plt.xlabel("Number images")

    plt.ylabel("Runtime (seconds)")
    plt.legend()
    plt.savefig("comparison_no_old_eager.png")

    # Run unit tests
    tf.test.main()
