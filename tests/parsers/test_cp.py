# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""Tests for the `CpParser`."""
import pytest

from aiida import orm
from aiida.common import AttributeDict

import numpy


#Now I use a post-6.5 git version (order of atom in the output changed)
@pytest.mark.parametrize('version', ['default', '6.5_autopilot', '6.5', '6.5_cgstep', '6.5_cgsteps'])
def test_cp_default(
    fixture_localhost, generate_calc_job_node, generate_parser, data_regression, generate_structure, version,
    call_something
):
    """Test a default `cp.x` calculation."""
    entry_point_calc_job = 'quantumespresso.cp'
    entry_point_parser = 'quantumespresso.cp'
    if version == 'default':

        def generate_inputs():
            return AttributeDict({
                'structure': generate_structure(structure_id='silicon'),
                'parameters': orm.Dict(dict={}),
            })
    else:

        def generate_inputs():
            return AttributeDict({
                'structure': generate_structure(structure_id='water'),
                'parameters': orm.Dict(dict={}),
            })

    node = generate_calc_job_node(entry_point_calc_job, fixture_localhost, version, generate_inputs())
    parser = generate_parser(entry_point_parser)
    results, calcfunction = parser.parse_from_node(node, store_provenance=False)

    assert calcfunction.is_finished, calcfunction.exception
    assert calcfunction.is_finished_ok, calcfunction.exit_message
    if version != '6.5_cgstep':
        #in a single cg step we don't have the trajectory output and a message is produced in the log
        assert not orm.Log.objects.get_logs_for(node)
    assert 'output_parameters' in results
    if version != '6.5_cgstep':
        assert 'output_trajectory' in results
        data_regression.check({
            'parameters':
            call_something(numpy.ndarray, 'tolist', results['output_parameters'].get_dict(), func=call_something),
            'trajectory':
            results['output_trajectory'].attributes
        })
    else:
        data_regression.check({
            'parameters':
            call_something(numpy.ndarray, 'tolist', results['output_parameters'].get_dict(), func=call_something),
        })
