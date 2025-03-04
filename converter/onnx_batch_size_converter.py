# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List, Set
import logging
import onnx.checker
from onnx import ModelProto, ValueInfoProto
from utils.argparse import ThrowingArgumentParser

def update_inputs_outputs_dims(
    model: ModelProto,
    input_dims: Dict[str, List[Any]],
    output_dims: Dict[str, List[Any]],
) -> ModelProto:
    """
    This function updates the dimension sizes of the model's inputs and outputs to the values
    provided in input_dims and output_dims. if the dim value provided is negative, a unique dim_param
    will be set for that dimension.
    Example. if we have the following shape for inputs and outputs:
            shape(input_1) = ('b', 3, 'w', 'h')
            shape(input_2) = ('b', 4)
            and shape(output)  = ('b', 'd', 5)
        The parameters can be provided as:
            input_dims = {
                "input_1": ['b', 3, 'w', 'h'],
                "input_2": ['b', 4],
            }
            output_dims = {
                "output": ['b', -1, 5]
            }
        Putting it together:
            model = onnx.load('model.onnx')
            updated_model = update_inputs_outputs_dims(model, input_dims, output_dims)
            onnx.save(updated_model, 'model.onnx')
    """
    dim_param_set: Set[str] = set()
    def init_dim_param_set(
        dim_param_set: Set[str], value_infos: List[ValueInfoProto]
    ) -> None:
        for info in value_infos:
            shape = info.type.tensor_type.shape
            for dim in shape.dim:
                if dim.HasField("dim_param"):
                    dim_param_set.add(dim.dim_param)  # type: ignore

    init_dim_param_set(dim_param_set, model.graph.input)  # type: ignore
    init_dim_param_set(dim_param_set, model.graph.output)  # type: ignore
    init_dim_param_set(dim_param_set, model.graph.value_info)  # type: ignore
    def update_dim(tensor: ValueInfoProto, dim: Any, j: int, name: str) -> None:
        dim_proto = tensor.type.tensor_type.shape.dim[j]
        if isinstance(dim, int):
            if dim >= 0:
                if dim_proto.HasField("dim_value") and dim_proto.dim_value != dim:
                    raise ValueError(
                        "Unable to set dimension value to {} for axis {} of {}. Contradicts existing dimension value {}.".format(
                            dim, j, name, dim_proto.dim_value
                        )
                    )
                dim_proto.dim_value = dim
            else:
                generated_dim_param = name + "_" + str(j)
                if generated_dim_param in dim_param_set:
                    raise ValueError(
                        "Unable to generate unique dim_param for axis {} of {}. Please manually provide a dim_param value.".format(
                            j, name
                        )
                    )
                dim_proto.dim_param = generated_dim_param
        elif isinstance(dim, str):
            dim_proto.dim_param = dim
        else:
            raise ValueError(
                f"Only int or str is accepted as dimension value, incorrect type: {type(dim)}"
            )
    for input in model.graph.input:
        input_name = input.name
        input_dim_arr = input_dims[input_name]
        for j, dim in enumerate(input_dim_arr):
            update_dim(input, dim, j, input_name)

    for output in model.graph.output:
        output_name = output.name
        output_dim_arr = output_dims[output_name]
        for j, dim in enumerate(output_dim_arr):
            update_dim(output, dim, j, output_name)
    onnx.checker.check_model(model)
    return model


if __name__ == "__main__":
    parser = ThrowingArgumentParser()
    parser.add_argument('--onnx', type=str, required=True, help='input onnx model path')
    parser.add_argument('--yaml', type=str, required=True, help='model input output dimension definitions file')
    parser.add_argument('--output', type=str, required=True, help='batch size updated output model file path')
    arguments, unknown_args = parser.parse_known_args()
    try:
        import onnx, yaml

        # load class info(.yaml)
        input_dims = {}
        output_dims = {}
        with open(arguments.yaml) as f:
            info = yaml.safe_load(f)
            input_dims = info.get('input_dims')
            output_dims = info.get('output_dims')

        model_onnx = onnx.load(arguments.onnx)  # load onnx model
        onnx.checker.check_model(model_onnx)  # check onnx model
        adjusted_batch_size_model = update_inputs_outputs_dims(model_onnx, input_dims, output_dims)
        logging.info(onnx.helper.printable_graph(adjusted_batch_size_model.graph))  # print
        onnx.save(adjusted_batch_size_model, arguments.output)
    except Exception as e:
        logging.info(f'Error occu{str(e)}')