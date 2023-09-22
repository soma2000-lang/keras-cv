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

from keras_cv.api_export import keras_cv_export
from keras_cv.backend import keras
from keras_cv.backend import ops
from keras_cv.models.segmentation.segment_anything.sam_layers import (
    RandomFrequencyPositionalEmbeddings,
)


@keras_cv_export("keras_cv.models.SAMPromptEncoder", package="keras_cv.models")
class SAMPromptEncoder(keras.layers.Layer):
    """Prompt Encoder for the Segment Anything Model (SAM).

    The prompt encoder generates encodings for three types of prompts:

    - Point prompts: Points on the image along with a label indicating whether
        the point is in the foreground (part of the mask) or in the background
        (not a part of the mask).
    - Box prompts: A batch of bounding boxes with format [(x1, y1), (x2, y2)]
        used to determine the location of the masks in the image.
    - Masks: An input mask can be passed to refine the positional embeddings
        for the output mask.

    First, the point prompts and box prompts are concatenated and positional
    encodings are generated using random spatial frequencies. A point is
    represented as the sum of a positional encoding of the point's location
    and one of two learned embeddings that indicate if the point is either in
    the foreground or background. A box is represented by an embedding pair:

    (1) the positional encoding of its top-left corner summed with a learned
    embedding representing "top-left corner" and
    (2) the same structure but using a learned embedding indicating
    "bottom-right corner".

    The box and point encodings are referred to as "sparse encodings"

    If a mask prompt is passed, a convolutional neural net is used to
    downscale it to generate "dense encodings". If no mask prompt is passed,
    an embedding layer is used instead to generate a "no mask" embedding.

    Args:
        embed_dim (int, optional): The number of features in the output
            embeddings. Defaults to `256`.
        image_embedding_size (int, optional): The number of features in the
            image embeddings generated by an image encoder. Defaults to
            `(64, 64)`.
        input_image_size (tuple[int], optional): A tuple of the height and
            width of the image being prompted. Defaults to `(1024, 1024)`.
        mask_in_chans (int, optional): The number of channels of the mask
            prompt. Defaults to `16`.
        activation (str, optional): The activation to use in the mask
            downscaler neural net. Defaults to `"gelu"`.

    References:
        - [Segment Anything paper](https://arxiv.org/abs/2304.02643)
        - [Segment Anything GitHub](https://github.com/facebookresearch/segment-anything)
    """  # noqa: E501

    def __init__(
        self,
        *,
        embed_dim=256,
        image_embedding_size=(64, 64),
        input_image_size=(1024, 1024),
        mask_in_chans=16,
        activation="gelu",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.embed_dim = embed_dim
        self.image_embedding_size = image_embedding_size
        self.input_image_size = input_image_size
        self.mask_in_chans = mask_in_chans
        self.activation = activation

        self.positional_embedding_layer = RandomFrequencyPositionalEmbeddings(
            num_positional_features=self.embed_dim // 2, scale=1
        )

        self.foreground_point_embed = keras.layers.Embedding(
            1, embed_dim, name="foreground_point_embed"
        )
        self.background_point_embed = keras.layers.Embedding(
            1, embed_dim, name="background_point_embed"
        )
        self.top_left_corner_embed = keras.layers.Embedding(
            1, embed_dim, name="top_left_corner_embed"
        )
        self.bottom_right_corner_embed = keras.layers.Embedding(
            1, embed_dim, name="bottom_right_corner_embed"
        )
        self.not_a_point_embed = keras.layers.Embedding(
            1, embed_dim, name="not_a_point_embed"
        )

        self.mask_downscaler = keras.models.Sequential(
            [
                keras.layers.Conv2D(
                    mask_in_chans // 4, kernel_size=2, strides=2
                ),
                keras.layers.LayerNormalization(epsilon=1e-6),
                keras.layers.Activation(activation),
                keras.layers.Conv2D(mask_in_chans, kernel_size=2, strides=2),
                keras.layers.LayerNormalization(epsilon=1e-6),
                keras.layers.Activation(activation),
                keras.layers.Conv2D(embed_dim, kernel_size=1),
            ],
            name="mask_downscaler",
        )
        self.no_mask_embed = keras.layers.Embedding(
            1, embed_dim, name="no_mask_embed"
        )

    def build(self, input_shape=None):
        self.positional_embedding_layer.build()
        for layer in [
            self.foreground_point_embed,
            self.background_point_embed,
            self.top_left_corner_embed,
            self.bottom_right_corner_embed,
            self.not_a_point_embed,
            self.no_mask_embed,
        ]:
            layer.build([None])
        self.mask_downscaler.build(
            [
                None,
                4 * self.image_embedding_size[0],
                4 * self.image_embedding_size[1],
                1,
            ]
        )
        self.built = True

    def compute_output_shape(self, input_shape):
        return {
            "sparse_embeddings": [None, None, self.embed_dim],
            "dense_embeddings": [
                None,
                self.image_embedding_size[0],
                self.image_embedding_size[1],
                self.embed_dim,
            ],
            "dense_positional_embeddings": [
                None,
                self.image_embedding_size[0],
                self.image_embedding_size[1],
                self.embed_dim,
            ],
        }

    def __embed_points(self, points, labels):
        points = points + 0.5
        indices = ops.arange(1, dtype="int32")

        point_embeddings = self.positional_embedding_layer.encode_coordinates(
            points, self.input_image_size
        )
        labels = ops.broadcast_to(
            labels[..., None], ops.shape(point_embeddings)
        )
        point_embeddings = ops.where(
            labels == 0,
            point_embeddings + self.background_point_embed(indices),
            point_embeddings + self.foreground_point_embed(indices),
        )
        point_embeddings = ops.where(
            labels == -1,
            self.not_a_point_embed(indices),
            point_embeddings,
        )
        return point_embeddings

    def __embed_box(self, box):
        shape = ops.shape(box)
        B, N = shape[0], shape[1]
        box = box + 0.5
        indices = ops.arange(1, dtype="int32")
        corner_embedding = self.positional_embedding_layer.encode_coordinates(
            box, self.input_image_size
        )
        top_left_embedding = corner_embedding[
            :, :, 0, :
        ] + self.top_left_corner_embed(indices)
        bottom_right_embedding = corner_embedding[
            :, :, 1, :
        ] + self.bottom_right_corner_embed(indices)
        corner_embedding = ops.stack(
            [top_left_embedding, bottom_right_embedding], axis=2
        )
        return ops.reshape(corner_embedding, (B, N * 2, self.embed_dim))

    def __embed_mask(self, mask):
        mask_embedding = self.mask_downscaler(mask)
        return mask_embedding

    def call(self, inputs):
        points, labels, box, mask = (
            inputs["points"],
            inputs["labels"],
            inputs["boxes"],
            inputs["masks"],
        )

        # Get the batch shape. Since all the inputs must have the
        # same batch shape, choose one input arbitrarily.
        B = ops.shape(points)[0]

        # Compute point embeddings
        point_embeddings = self.__embed_points(points, labels)

        # Compute box embeddings
        box_embeddings = self.__embed_box(box)

        # Concatenate both into a sparse embeddings tensor
        sparse_embeddings = ops.concatenate(
            [point_embeddings, box_embeddings], axis=1
        )

        # Compute the mask embeddings
        _no_mask_embed = lambda: (
            ops.broadcast_to(
                ops.reshape(
                    self.no_mask_embed(ops.arange(1, dtype="int32")),
                    (1, 1, 1, self.embed_dim),
                ),
                shape=(
                    B,
                    self.image_embedding_size[0],
                    self.image_embedding_size[1],
                    self.embed_dim,
                ),
            )
        )

        def _maybe_input_mask_embed():
            # Keras Core passes the masks as concrete tensors for both the
            # true and false functions to build the output shape. So, we
            # need to handle the case when 0 size mask is passed and
            # dispatch the call to `_no_mask_embed`. Note that we can't call
            # the lambda directly since the inputs are bound to different
            # values when called with concrete values.
            if mask.shape[1] == 0:
                return ops.broadcast_to(
                    ops.reshape(
                        self.no_mask_embed(ops.arange(1, dtype="int32")),
                        (1, 1, 1, self.embed_dim),
                    ),
                    shape=(
                        B,
                        self.image_embedding_size[0],
                        self.image_embedding_size[1],
                        self.embed_dim,
                    ),
                )
            shape = ops.shape(mask)
            BM, N, H, W, C = shape[0], shape[1], shape[2], shape[3], shape[4]
            return self.__embed_mask(ops.reshape(mask, (BM * N, H, W, C)))

        dense_embeddings = ops.cond(
            ops.equal(ops.size(mask), 0),
            _no_mask_embed,
            _maybe_input_mask_embed,
        )

        # Compute the dense positional embeddings
        dense_positional_embeddings = (
            self.positional_embedding_layer.encode_image(
                self.image_embedding_size
            )[None, ...]
        )

        return {
            "sparse_embeddings": sparse_embeddings,
            "dense_embeddings": dense_embeddings,
            "dense_positional_embeddings": dense_positional_embeddings,
        }

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "embed_dim": self.embed_dim,
                "image_embedding_size": self.image_embedding_size,
                "input_image_size": self.input_image_size,
                "mask_in_chans": self.mask_in_chans,
                "activation": self.activation,
            }
        )
        return config