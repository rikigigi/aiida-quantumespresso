# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,too-many-statements
"""Initialise a text database and profile for pytest."""
import io
import os
import collections
import pytest

pytest_plugins = ['aiida.manage.tests.pytest_fixtures']  # pylint: disable=invalid-name


@pytest.fixture(scope='session')
def filepath_tests():
    """Return the absolute filepath of the `tests` folder.

    .. warning:: if this file moves with respect to the `tests` folder, the implementation should change.

    :return: absolute filepath of `tests` folder which is the basepath for all test resources.
    """
    return os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def filepath_fixtures(filepath_tests):
    """Return the absolute filepath to the directory containing the file `fixtures`."""
    return os.path.join(filepath_tests, 'fixtures')


@pytest.fixture(scope='function')
def fixture_sandbox():
    """Return a `SandboxFolder`."""
    from aiida.common.folders import SandboxFolder
    with SandboxFolder() as folder:
        yield folder


@pytest.fixture
def fixture_localhost(aiida_localhost):
    """Return a localhost `Computer`."""
    localhost = aiida_localhost
    localhost.set_default_mpiprocs_per_machine(1)
    return localhost


@pytest.fixture
def fixture_code(fixture_localhost):
    """Return a `Code` instance configured to run calculations of given entry point on localhost `Computer`."""

    def _fixture_code(entry_point_name):
        from aiida.orm import Code
        return Code(input_plugin_name=entry_point_name, remote_computer_exec=[fixture_localhost, '/bin/true'])

    return _fixture_code


@pytest.fixture
def generate_calc_job():
    """Fixture to construct a new `CalcJob` instance and call `prepare_for_submission` for testing `CalcJob` classes.

    The fixture will return the `CalcInfo` returned by `prepare_for_submission` and the temporary folder that was passed
    to it, into which the raw input files will have been written.
    """

    def _generate_calc_job(folder, entry_point_name, inputs=None):
        """Fixture to generate a mock `CalcInfo` for testing calculation jobs."""
        from aiida.engine.utils import instantiate_process
        from aiida.manage.manager import get_manager
        from aiida.plugins import CalculationFactory

        manager = get_manager()
        runner = manager.get_runner()

        process_class = CalculationFactory(entry_point_name)
        process = instantiate_process(runner, process_class, **inputs)

        calc_info = process.prepare_for_submission(folder)

        return calc_info

    return _generate_calc_job


@pytest.fixture
def generate_calc_job_node(fixture_localhost):
    """Fixture to generate a mock `CalcJobNode` for testing parsers."""

    def flatten_inputs(inputs, prefix=''):
        """Flatten inputs recursively like :meth:`aiida.engine.processes.process::Process._flatten_inputs`."""
        flat_inputs = []
        for key, value in inputs.items():
            if isinstance(value, collections.Mapping):
                flat_inputs.extend(flatten_inputs(value, prefix=prefix + key + '__'))
            else:
                flat_inputs.append((prefix + key, value))
        return flat_inputs

    def _generate_calc_job_node(entry_point_name='base', computer=None, test_name=None, inputs=None, attributes=None):
        """Fixture to generate a mock `CalcJobNode` for testing parsers.

        :param entry_point_name: entry point name of the calculation class
        :param computer: a `Computer` instance
        :param test_name: relative path of directory with test output files in the `fixtures/{entry_point_name}` folder.
        :param inputs: any optional nodes to add as input links to the corrent CalcJobNode
        :param attributes: any optional attributes to set on the node
        :return: `CalcJobNode` instance with an attached `FolderData` as the `retrieved` node
        """
        from aiida import orm
        from aiida.common import LinkType
        from aiida.plugins.entry_point import format_entry_point_string

        if computer is None:
            computer = fixture_localhost

        filepath_folder = None

        if test_name is not None:
            basepath = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.join(entry_point_name[len('quantumespresso.'):], test_name)
            filepath_folder = os.path.join(basepath, 'parsers', 'fixtures', filename)
            filepath_input = os.path.join(filepath_folder, 'aiida.in')

        entry_point = format_entry_point_string('aiida.calculations', entry_point_name)

        node = orm.CalcJobNode(computer=computer, process_type=entry_point)
        node.set_attribute('input_filename', 'aiida.in')
        node.set_attribute('output_filename', 'aiida.out')
        node.set_attribute('error_filename', 'aiida.err')
        node.set_option('resources', {'num_machines': 1, 'num_mpiprocs_per_machine': 1})
        node.set_option('max_wallclock_seconds', 1800)

        if attributes:
            node.set_attribute_many(attributes)

        if filepath_folder:
            from qe_tools.utils.exceptions import ParsingError
            from aiida_quantumespresso.tools.pwinputparser import PwInputFile
            try:
                parsed_input = PwInputFile(filepath_input)
            except ParsingError:
                pass
            else:
                inputs['structure'] = parsed_input.get_structuredata()
                inputs['parameters'] = orm.Dict(dict=parsed_input.namelists)

        if inputs:
            metadata = inputs.pop('metadata', {})
            options = metadata.get('options', {})

            for name, option in options.items():
                node.set_option(name, option)

            for link_label, input_node in flatten_inputs(inputs):
                input_node.store()
                node.add_incoming(input_node, link_type=LinkType.INPUT_CALC, link_label=link_label)

        node.store()

        if filepath_folder:
            retrieved = orm.FolderData()
            retrieved.put_object_from_tree(filepath_folder)
            retrieved.add_incoming(node, link_type=LinkType.CREATE, link_label='retrieved')
            retrieved.store()

            remote_folder = orm.RemoteData(computer=computer, remote_path='/tmp')
            remote_folder.add_incoming(node, link_type=LinkType.CREATE, link_label='remote_folder')
            remote_folder.store()

        return node

    return _generate_calc_job_node


@pytest.fixture(scope='session')
def generate_upf_data(filepath_tests):
    """Return a `UpfData` instance for the given element a file for which should exist in `tests/fixtures/pseudos`."""

    def _generate_upf_data(element):
        """Return `UpfData` node."""
        from aiida.orm import UpfData

        filepath = os.path.join(filepath_tests, 'fixtures', 'pseudos', '{}.upf'.format(element))

        with io.open(filepath, 'r') as handle:
            upf = UpfData(file=handle.name)

        return upf

    return _generate_upf_data


@pytest.fixture
def generate_structure():
    """Return a `StructureData` representing bulk silicon."""

    def _generate_structure(structure_id='silicon'):
        """Return a `StructureData` representing bulk silicon or a snapshot of a single water molecule dynamics."""
        from aiida.orm import StructureData

        if structure_id == 'silicon':
            param = 5.43
            cell = [[param / 2., param / 2., 0], [param / 2., 0, param / 2.], [0, param / 2., param / 2.]]
            structure = StructureData(cell=cell)
            structure.append_atom(position=(0., 0., 0.), symbols='Si', name='Si')
            structure.append_atom(position=(param / 4., param / 4., param / 4.), symbols='Si', name='Si')
        elif structure_id == 'water':
            structure = StructureData(cell=[[5.29177209, 0., 0.], [0., 5.29177209, 0.], [0., 0., 5.29177209]])
            structure.append_atom(position=[12.73464656, 16.7741411, 24.35076238], symbols='H', name='H')
            structure.append_atom(position=[-29.3865565, 9.51707929, -4.02515904], symbols='H', name='H')
            structure.append_atom(position=[1.04074437, -1.64320127, -1.27035021], symbols='O', name='O')
        else:
            raise KeyError('Unknown structure_id=\'{}\''.format(structure_id))
        return structure

    return _generate_structure


@pytest.fixture
def generate_kpoints_mesh():
    """Return a `KpointsData` node."""

    def _generate_kpoints_mesh(npoints):
        """Return a `KpointsData` with a mesh of npoints in each direction."""
        from aiida.orm import KpointsData

        kpoints = KpointsData()
        kpoints.set_kpoints_mesh([npoints] * 3)

        return kpoints

    return _generate_kpoints_mesh


@pytest.fixture(scope='session')
def generate_parser():
    """Fixture to load a parser class for testing parsers."""

    def _generate_parser(entry_point_name):
        """Fixture to load a parser class for testing parsers.

        :param entry_point_name: entry point name of the parser class
        :return: the `Parser` sub class
        """
        from aiida.plugins import ParserFactory
        return ParserFactory(entry_point_name)

    return _generate_parser


@pytest.fixture
def generate_remote_data():
    """Return a `RemoteData` node."""

    def _generate_remote_data(computer, remote_path, entry_point_name=None):
        """Return a `KpointsData` with a mesh of npoints in each direction."""
        from aiida.common.links import LinkType
        from aiida.orm import CalcJobNode, RemoteData
        from aiida.plugins.entry_point import format_entry_point_string

        entry_point = format_entry_point_string('aiida.calculations', entry_point_name)

        remote = RemoteData(remote_path=remote_path)
        remote.computer = computer

        if entry_point_name is not None:
            creator = CalcJobNode(computer=computer, process_type=entry_point)
            creator.set_option('resources', {'num_machines': 1, 'num_mpiprocs_per_machine': 1})
            remote.add_incoming(creator, link_type=LinkType.CREATE, link_label='remote_folder')
            creator.store()

        return remote

    return _generate_remote_data


@pytest.fixture
def generate_workchain():
    """Generate an instance of a `WorkChain`."""

    def _generate_workchain(entry_point, inputs):
        """Generate an instance of a `WorkChain` with the given entry point and inputs.

        :param entry_point: entry point name of the work chain subclass.
        :param inputs: inputs to be passed to process construction.
        :return: a `WorkChain` instance.
        """
        from aiida.engine.utils import instantiate_process
        from aiida.manage.manager import get_manager
        from aiida.plugins import WorkflowFactory

        process_class = WorkflowFactory(entry_point)
        runner = get_manager().get_runner()
        process = instantiate_process(runner, process_class, **inputs)

        return process

    return _generate_workchain


@pytest.fixture
def generate_inputs_matdyn(filepath_tests, fixture_code, generate_kpoints_mesh):
    """Generate default inputs for a `MatdynCalculation."""

    def _generate_inputs_matdyn():
        """Generate default inputs for a `MatdynCalculation."""
        from aiida_quantumespresso.data.force_constants import ForceConstantsData
        from aiida_quantumespresso.utils.resources import get_default_options

        filepath = os.path.join(filepath_tests, 'calculations', 'fixtures', 'matdyn', 'default', 'force_constants.dat')

        inputs = {
            'code': fixture_code('quantumespresso.matdyn'),
            'force_constants': ForceConstantsData(filepath),
            'kpoints': generate_kpoints_mesh(2),
            'metadata': {
                'options': get_default_options()
            }
        }

        return inputs

    return _generate_inputs_matdyn


@pytest.fixture
def generate_inputs_q2r(fixture_sandbox, fixture_localhost, fixture_code, generate_remote_data):
    """Generate default inputs for a `Q2rCalculation."""

    def _generate_inputs_q2r():
        """Generate default inputs for a `Q2rCalculation."""
        from aiida_quantumespresso.utils.resources import get_default_options

        inputs = {
            'code': fixture_code('quantumespresso.q2r'),
            'parent_folder': generate_remote_data(fixture_localhost, fixture_sandbox.abspath, 'quantumespresso.ph'),
            'metadata': {
                'options': get_default_options()
            }
        }

        return inputs

    return _generate_inputs_q2r


@pytest.fixture
def generate_inputs_ph(fixture_sandbox, fixture_localhost, fixture_code, generate_remote_data, generate_kpoints_mesh):
    """Generate default inputs for a `PhCalculation."""

    def _generate_inputs_ph():
        """Generate default inputs for a `PhCalculation."""
        from aiida.orm import Dict
        from aiida_quantumespresso.utils.resources import get_default_options

        inputs = {
            'code': fixture_code('quantumespresso.matdyn'),
            'parent_folder': generate_remote_data(fixture_localhost, fixture_sandbox.abspath, 'quantumespresso.pw'),
            'qpoints': generate_kpoints_mesh(2),
            'parameters': Dict(dict={'INPUTPH': {}}),
            'metadata': {
                'options': get_default_options()
            }
        }

        return inputs

    return _generate_inputs_ph


@pytest.fixture
def generate_inputs_pw(fixture_code, generate_structure, generate_kpoints_mesh, generate_upf_data):
    """Generate default inputs for a `PwCalculation."""

    def _generate_inputs_pw():
        """Generate default inputs for a `PwCalculation."""
        from aiida.orm import Dict
        from aiida_quantumespresso.utils.resources import get_default_options

        inputs = {
            'code': fixture_code('quantumespresso.pw'),
            'structure': generate_structure(),
            'kpoints': generate_kpoints_mesh(2),
            'parameters': Dict(dict={
                'CONTROL': {
                    'calculation': 'scf'
                },
                'SYSTEM': {
                    'ecutrho': 240.0,
                    'ecutwfc': 30.0
                }
            }),
            'pseudos': {
                'Si': generate_upf_data('Si')
            },
            'metadata': {
                'options': get_default_options()
            }
        }

        return inputs

    return _generate_inputs_pw


@pytest.fixture
def generate_inputs_cp(fixture_code, generate_structure, generate_upf_data):
    """Generate default inputs for a CpCalculation."""

    def _generate_inputs_cp(autopilot=False):
        """Generate default inputs for a CpCalculation."""
        from aiida.orm import Dict
        from aiida_quantumespresso.utils.resources import get_default_options

        inputs = {
            'code': fixture_code('quantumespresso.cp'),
            'structure': generate_structure(),
            'parameters': Dict(dict={
                'CONTROL': {
                    'calculation': 'cp'
                },
                'SYSTEM': {
                    'ecutrho': 240.0,
                    'ecutwfc': 30.0
                }
            }),
            'pseudos': {
                'Si': generate_upf_data('Si')
            },
            'metadata': {
                'options': get_default_options()
            }
        }
        if autopilot:
            inputs['settings'] = Dict(
                dict={
                    'AUTOPILOT': [{
                        'onstep': 2,
                        'what': 'dt',
                        'newvalue': 42.0
                    }, {
                        'onstep': 3,
                        'what': 'dt',
                        'newvalue': 42.42
                    }]
                }
            )

        return inputs

    return _generate_inputs_cp


@pytest.fixture
def call_something():
    """Recursive (in dict and list) member function application.

    Return a function to do a recursive substitution of element,
    with getattr(element, what), where what is provided.
    """

    def _do_stuff(class_type, what, data, func=call_something, **kwargs):
        """Recursive call to a member function of a particular type on a iterable structure of dict and list."""
        if isinstance(data, class_type):
            return getattr(data, what)(**kwargs)
        if isinstance(data, list):
            return [func(class_type, what, _, func=func, **kwargs) for _ in data]
        if isinstance(data, dict):
            return {key: func(class_type, what, data[key], func=func, **kwargs) for key in data}
        return data

    return _do_stuff
