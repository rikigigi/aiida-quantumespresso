"""Tests for the `NebCalculation` class."""

import pytest
from aiida import orm

from aiida_quantumespresso.calculations.neb import NebCalculation


def test_neb_calcjob_validation(fixture_sandbox, generate_calc_job, generate_inputs):
    """Test that the `NebCalculation` still uses the `CalcJob` top-level input validation."""
    entry_point_name = 'quantumespresso.neb'

    inputs = generate_inputs(entry_point_name)
    inputs['metadata'] = {'options': {'resources': {'non-existent': 1}}}
    with pytest.raises(ValueError, match='input `metadata.options.resources` is not valid for the'):
        generate_calc_job(fixture_sandbox, entry_point_name, inputs)


def test_parameters_validation():
    """Test the validation of the `parameters` input."""

    builder = NebCalculation.get_builder()

    parameters = {'path': {'num_of_images': 8}}

    with pytest.warns(UserWarning, match="'path' should be UPPERCASE"):
        builder.parameters = parameters

    assert builder.parameters.get_dict() == {'PATH': {'num_of_images': 8}}

    with pytest.raises(ValueError, match="'path' should be UPPERCASE"):
        builder.parameters = orm.Dict(parameters).store()


@pytest.fixture
def generate_inputs_neb(fixture_code, generate_structure, generate_upf_data, generate_kpoints_mesh):
    """Generate inputs for a `NebCalculation` with an `images` trajectory."""

    def _generate_inputs_neb(num_of_images=3, images=3):
        first_structure = generate_structure()
        inputs = {
            'parameters': orm.Dict(dict={'PATH': {'num_of_images': num_of_images}}),
            'code': fixture_code('quantumespresso.neb'),
            'pw': {
                'parameters': orm.Dict(
                    {
                        'CONTROL': {'calculation': 'scf'},
                        'SYSTEM': {'ecutrho': 240.0, 'ecutwfc': 30.0},
                        'ELECTRONS': {'electron_maxstep': 60},
                    }
                ),
                'kpoints': generate_kpoints_mesh(2),
                'pseudos': {kind: generate_upf_data(kind) for kind in first_structure.get_kind_names()},
            },
        }
        if isinstance(images, list):
            inputs['images'] = images
        elif isinstance(images, int):
            image_list = [generate_structure() for _ in range(images)]
            inputs['images'] = orm.TrajectoryData(image_list)
        else:
            raise ValueError('images should be either an integer or a list of structures.')

        return inputs

    return _generate_inputs_neb


@pytest.mark.parametrize('num_of_images', [3, 5])
def test_neb_default(fixture_sandbox, generate_calc_job, generate_inputs_neb, file_regression, num_of_images):
    """Test the input file generation of a default NEB calculation with an `images` trajectory."""
    entry_point_name = 'quantumespresso.neb'
    inputs = generate_inputs_neb(num_of_images=num_of_images, images=num_of_images)
    calc_info = generate_calc_job(fixture_sandbox, entry_point_name, inputs)

    assert 'aiida.out' in calc_info.retrieve_list
    with fixture_sandbox.open('neb.dat') as handle:
        input_written = handle.read()
    file_regression.check(input_written, encoding='utf-8', extension='.dat')
    assert sorted(fixture_sandbox.get_content_list()) == sorted(
        ['neb.dat', 'out', 'pseudo'] + [f'pw_{i + 1}.in' for i in range(num_of_images)]
    )
    for i in range(num_of_images):
        with fixture_sandbox.open(f'pw_{i + 1}.in') as handle:
            pw_input_written = handle.read()
        file_regression.check(pw_input_written, encoding='utf-8', extension=f'.pw{i + 1}.in')
