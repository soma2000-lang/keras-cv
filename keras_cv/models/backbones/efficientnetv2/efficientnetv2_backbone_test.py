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

import tensorflow as tf
from absl.testing import parameterized

from keras_cv.models.backbones.efficientnetv2 import efficientnetv2_backbone

from .models_test import ModelsTest

MODEL_LIST = [
    (efficientnetv2_backbone.EfficientNetV2B0, 1280, {}),
]

"""
Below are other configurations that we omit from our CI but that can/should
be tested manually when making changes to this model.
(efficientnetv2.EfficientNetV2B1, 1280, {}),
(efficientnetv2.EfficientNetV2B2, 1408, {}),
(efficientnetv2.EfficientNetV2B3, 1536, {}),
(efficientnetv2.EfficientNetV2S, 1280, {}),
(efficientnetv2.EfficientNetV2M, 1280, {}),
(efficientnetv2.EfficientNetV2L, 1280, {}),
"""


class EfficientNetV2Test(ModelsTest, tf.test.TestCase, parameterized.TestCase):
    @parameterized.parameters(*MODEL_LIST)
    def test_application_base(self, app, _, args):
        super()._test_application_base(app, _, args)

    @parameterized.parameters(*MODEL_LIST)
    def test_application_with_rescaling(self, app, last_dim, args):
        super()._test_application_with_rescaling(app, last_dim, args)

    @parameterized.parameters(*MODEL_LIST)
    def test_application_pooling(self, app, last_dim, args):
        super()._test_application_pooling(app, last_dim, args)

    @parameterized.parameters(*MODEL_LIST)
    def test_application_variable_input_channels(self, app, last_dim, args):
        super()._test_application_variable_input_channels(app, last_dim, args)

    @parameterized.parameters(*MODEL_LIST)
    def test_model_can_be_used_as_backbone(self, app, last_dim, args):
        super()._test_model_can_be_used_as_backbone(app, last_dim, args)


if __name__ == "__main__":
    tf.test.main()
