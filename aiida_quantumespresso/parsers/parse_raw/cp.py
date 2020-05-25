# -*- coding: utf-8 -*-
from xml.dom.minidom import parseString
from xmlschema import XMLSchema
from xmlschema.etree import ElementTree

from aiida_quantumespresso.parsers import QEOutputParsingError, get_parser_info
from aiida_quantumespresso.parsers.parse_xml.pw.legacy import (read_xml_card,
                   parse_xml_child_integer,xml_card_header,parse_xml_child_bool,
                   parse_xml_child_str,parse_xml_child_float,
                   parse_xml_child_attribute_str,xml_card_cell,xml_card_ions,
                   xml_card_exchangecorrelation,xml_card_spin,xml_card_planewaves)
from aiida_quantumespresso.parsers.parse_xml.pw.parse import parse_pw_xml_post_6_2
from aiida_quantumespresso.parsers.parse_xml.pw.versions import get_xml_file_version, get_schema_filepath, get_default_schema_filepath, QeXmlVersion
#TODO: check if we have to remove this
from six.moves import range


def parse_cp_traj_stanzas(num_elements, splitlines, prepend_name, rescale=1.):
    """
    num_elements: Number of lines (with three elements) between lines with two only
    elements (containing step number and time in ps).
    num_elements is 3 for cell, and the number of atoms for coordinates and positions.

    splitlines: a list of lines of the file, already split in pieces using string.split

    prepend_name: a string to be prepended to the name of keys returned
    in the return dictionary.

    rescale: the values in each stanza are multiplied by this factor, for units conversion
    """
    steps = []
    times = []
    stanzas = []
    this_stanza = []
    start_stanza = False
    linenum = -1
    try:
        for linenum, l in enumerate(splitlines):
            if len(l) == 2:
                steps.append(int(l[0]))
                times.append(float(l[1]))
                start_stanza = True
                if len(this_stanza) != 0:
                    raise ValueError('Wrong position of short line.')
            elif len(l) == 3:
                if len(this_stanza) == 0 and not start_stanza:
                    raise ValueError('Wrong position of long line.')
                start_stanza = False
                this_stanza.append([float(l[0]) * rescale, float(l[1]) * rescale, float(l[2]) * rescale])
                if len(this_stanza) == num_elements:
                    stanzas.append(this_stanza)
                    this_stanza = []
            else:
                raise ValueError('Wrong line length ({})'.format(len(l)))
        if len(this_stanza) != 0:
            raise ValueError('Wrong length of last block ({} lines instead of 0).'.format(len(this_stanza)))
        if len(steps) != len(stanzas):
            raise ValueError('Length mismatch between number of steps and number of defined stanzas.')
        return {
            '{}_steps'.format(prepend_name): steps,
            '{}_times'.format(prepend_name): times,
            '{}_data'.format(prepend_name): stanzas,
        }
    except Exception as e:
        e.message = 'At line {}: {}'.format(linenum + 1, e)
        raise e


def parse_cp_text_output(data, xml_data):
    """data must be a list of strings, one for each lines, as returned by readlines().

    On output, a dictionary with parsed values
    """
    # TODO: uniform readlines() and read() usage for passing input to the parser

    parsed_data = {}
    parsed_data['warnings'] = []

    for count, line in enumerate(data):

        if 'warning' in line.lower():
            parsed_data['warnings'].append(line)
        elif 'bananas' in line:
            parsed_data['warnings'].append('Bananas from the ortho.')
        elif 'CP' in line and 'WALL' in line:
            try:
                time = line.split('CPU')[1].split('WALL')[0]
                parsed_data['wall_time'] = time
            except:
                raise QEOutputParsingError('Error while parsing wall time.')
    try:
        for count,line in enumerate(reversed(data)):
            if 'nfi' in line and 'ekinc' in line and 'econs' in line:
                this_line = data[len(data)-count]
                try:
                    parsed_data['ekinc'] = [float(this_line.split()[1])]
                except ValueError:
                    pass
                try:
                    parsed_data['temph'] = [float(this_line.split()[2])]
                except ValueError:
                    pass
                try:
                    parsed_data['tempp'] = [float(this_line.split()[3])]
                except ValueError:
                    pass
                try:
                    parsed_data['etot'] = [float(this_line.split()[4])]
                except ValueError:
                    pass
                try:
                    parsed_data['enthal'] = [float(this_line.split()[5])]
                except ValueError:
                    pass
                try:
                    parsed_data['econs'] = [float(this_line.split()[6])]
                except ValueError:
                    pass
                try:
                    parsed_data['econt'] = [float(this_line.split()[7])]
                except ValueError:
                    pass
                try:
                    parsed_data['vnhh'] = [float(this_line.split()[8])]
                except (ValueError, IndexError):
                    pass
                try:
                    parsed_data['xnhh0'] = [float(this_line.split()[9])]
                except (ValueError, IndexError):
                    pass
                try:
                    parsed_data['vnhp'] = [float(this_line.split()[10])]
                except (ValueError, IndexError):
                    pass
                try:
                    parsed_data['xnhp0'] = [float(this_line.split()[11])]
                except (ValueError, IndexError):
                    pass
    except Exception as e:
        print(e)

    return parsed_data


def parse_cp_xml_counter_output(data):
    """Parse xml file print_counter.xml data must be a single string, as returned by file.read() (notice the difference
    with parse_text_output!) On output, a dictionary with parsed values."""
    dom = parseString(data)
    parsed_data = {}
    cardname = 'LAST_SUCCESSFUL_PRINTOUT'

    card1 = [_ for _ in dom.childNodes if _.nodeName == 'PRINT_COUNTER'][0]
    card2 = [_ for _ in card1.childNodes if _.nodeName == 'LAST_SUCCESSFUL_PRINTOUT'][0]

    tagname = 'STEP'
    parsed_data[cardname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, card2)

    return parsed_data

def parse_cp_counter_output(data):
    """Parse xml file print_counter data must be a single string, as returned by file.read() (notice the difference
    with parse_text_output!) On output, a dictionary with parsed values."""
    parsed_data={}
    cardname='LAST_SUCCESSFUL_PRINTOUT'
    tagname='STEP'
    numbers = [int(s) for s in data.split() if s.isdigit()]
    if numbers:
        parsed_data[cardname.lower().replace('-','_')] = numbers[0]

    return parsed_data



def parse_cp_raw_output(out_file, xml_file=None, xml_counter_file=None,print_counter_xml=True):

    parser_info = get_parser_info(parser_info_template='aiida-quantumespresso parser cp.x v{}')

    # analyze the xml
    if xml_file is not None:
        xml_parsed = ElementTree.parse(xml_file)
        xml_file_version = get_xml_file_version(xml_parsed)
        if xml_file_version == QeXmlVersion.POST_6_2:
            xml_data, logs = parse_pw_xml_post_6_2(xml_parsed)
        elif xml_file_version == QeXmlVersion.PRE_6_2:
            xml_file.seek(0)
            xml_data = parse_cp_xml_output(xml_file.read())
    else:
        parser_info['parser_warnings'].append('Skipping the parsing of the xml file.')
        xml_data = {}

    # analyze the counter file, which keeps info on the steps
    if xml_counter_file is not None:
        if print_counter_xml:
            xml_counter_data = parse_cp_xml_counter_output(xml_counter_file.read())
        else:
            xml_counter_data = parse_cp_counter_output(xml_counter_file.read())
    else:
        xml_counter_data = {}

    # analyze the standard output
    out_lines = out_file.readlines()

    # understand if the job ended smoothly
    job_successful = any('JOB DONE' in line for line in reversed(out_lines))

    out_data = parse_cp_text_output(out_lines, xml_data)

    for key in out_data.keys():
        if key in list(xml_data.keys()):
            raise AssertionError('%s found in both dictionaries' % key)
        if key in list(xml_counter_data.keys()):
            raise AssertionError('%s found in both dictionaries' % key)
        # out_data keys take precedence and overwrite xml_data keys,
        # if the same key name is shared by both (but this should not happen!)

    final_data = dict(list(xml_data.items()) + list(out_data.items()) + list(xml_counter_data.items()))

    # TODO: parse the trajectory and save them in a reasonable format

    return final_data, job_successful


# TODO: the xml has a lot in common with pw, maybe I should avoid duplication of code
# or maybe should I wait for the new version of data-file.xml ?
def parse_cp_xml_output(data):
    """Parse xml data data must be a single string, as returned by file.read() (notice the difference with
    parse_text_output!) On output, a dictionary with parsed values.

    Democratically, we have decided to use picoseconds as units of time, eV for energies, Angstrom for lengths.
    """
    import copy

    dom = parseString(data)

    parsed_data = {}

    #CARD HEADER
    try:
        parsed_data = copy.deepcopy(xml_card_header(parsed_data, dom))
    except Exception as e:
        print(e)

    # CARD CONTROL

    cardname='CONTROL'
    try:
        target_tags = read_xml_card(dom, cardname)
    except Exception as e:
        print(e)


    tagname='PP_CHECK_FLAG'
    try:
        parsed_data[tagname.lower()] = parse_xml_child_bool(tagname, target_tags)
    except Exception as e:
        print(e)


    # CARD STATUS

    cardname = 'STATUS'
    try:
        target_tags = read_xml_card(dom,cardname)
    except Exception as e:
        print(e)


    tagname = 'STEP'
    attrname = 'ITERATION'
    try:
        parsed_data[(tagname+'_'+attrname).lower()]=int(parse_xml_child_attribute_str(tagname,attrname,target_tags))
    except Exception as e:
        print(e)


    tagname = 'TIME'
    attrname = 'UNITS'
    try:
        value=parse_xml_child_float(tagname,target_tags)
    except Exception as e:
        print(e)

    try:
        units = parse_xml_child_attribute_str(tagname,attrname,target_tags)
        if units not in ['pico-seconds']:
            raise QEOutputParsingError('Units {} are not supported by parser'.format(units))
        parsed_data[tagname.lower()]=value
    except Exception as e:
        print(e)


    tagname = 'TITLE'
    try:
        parsed_data[tagname.lower()]=parse_xml_child_str(tagname,target_tags)
    except Exception as e:
        print(e)


    # CARD CELL
    try:
        parsed_data,lattice_vectors,volume = copy.deepcopy(xml_card_cell(parsed_data,dom))
    except Exception as e:
        print(e)


    # CARD IONS
    try:
        parsed_data = copy.deepcopy(xml_card_ions(parsed_data,dom,lattice_vectors,volume))
    except Exception as e:
        print(e)


    # CARD PLANE WAVES

    try:
        parsed_data = copy.deepcopy(xml_card_planewaves(parsed_data,dom,'cp'))
    except Exception as e:
        print(e)


    # CARD SPIN
    try:
        parsed_data = copy.deepcopy(xml_card_spin(parsed_data,dom))
    except Exception as e:
        print(e)


    # CARD EXCHANGE_CORRELATION
    try:
        parsed_data = copy.deepcopy(xml_card_exchangecorrelation(parsed_data,dom))
    except Exception as e:
        print(e)


    # TODO CARD OCCUPATIONS

    # CARD BRILLOUIN ZONE
    # TODO: k points are saved for CP... Why?

    cardname='BRILLOUIN_ZONE'
    try:
        target_tags=read_xml_card(dom, cardname)
    except Exception as e:
        print(e)


    tagname='NUMBER_OF_K-POINTS'
    try:
        parsed_data[tagname.replace('-','_').lower()] = parse_xml_child_integer(tagname, target_tags)
    except Exception as e:
        print(e)


    tagname='UNITS_FOR_K-POINTS'
    attrname='UNITS'
    try:
        metric=parse_xml_child_attribute_str(tagname,attrname,target_tags)
        if metric not in ['2 pi / a']:
            raise QEOutputParsingError('Error parsing attribute %s, tag %s inside %s, units unknown'% (attrname,tagname, target_tags.tagName ) )
        parsed_data[tagname.replace('-','_').lower()]=metric
    except Exception as e:
        print(e)


    # TODO: check what happens if one does not use the monkhorst pack in the code
    tagname = 'MONKHORST_PACK_GRID'
    try:
        try:
            a=target_tags.getElementsByTagName(tagname)[0]
            value=[int(a.getAttribute('nk'+str(i+1))) for i in range(3)]
            parsed_data[tagname.replace('-','_').lower()]=value
        except:
            raise QEOutputParsingError('Error parsing tag %s inside %s.'% (tagname, target_tags.tagName ) )

        tagname='MONKHORST_PACK_OFFSET'
        try:
            a=target_tags.getElementsByTagName(tagname)[0]
            value=[int(a.getAttribute('k'+str(i+1))) for i in range(3)]
            parsed_data[tagname.replace('-','_').lower()]=value
        except:
            raise QEOutputParsingError('Error parsing tag %s inside %s.'% (tagname, target_tags.tagName ) )

        try:
            kpoints=[]
            for i in range(parsed_data['number_of_k_points']):
                tagname='K-POINT.'+str(i+1)
                a=target_tags.getElementsByTagName(tagname)[0]
                b=a.getAttribute('XYZ').replace('\n','').rsplit()
                value=[ float(s) for s in b ]

                metric=parsed_data['units_for_k_points']
                if metric=='2 pi / a':
                    value=[ float(s)/parsed_data['lattice_parameter'] for s in value ]

                    weight=float(a.getAttribute('WEIGHT'))

                    kpoints.append([value,weight])

            parsed_data['k_point']=kpoints
        except:
            raise QEOutputParsingError('Error parsing tag K-POINT.# inside %s.'% (target_tags.tagName ) )

        tagname='NORM-OF-Q'
        # TODO decide if save this parameter
        parsed_data[tagname.replace('-','_').lower()]=parse_xml_child_float(tagname,target_tags)
    except Exception as e:
        print(e)

    # CARD PARALLELISM
    # can be optional

    try:
        cardname = 'PARALLELISM'
        target_tags = read_xml_card(dom, cardname)

        tagname = 'GRANULARITY_OF_K-POINTS_DISTRIBUTION'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS_PER_POOL'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS_PER_IMAGE'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS_PER_TASKGROUP'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS_PER_POT'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS_PER_BAND_GROUP'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)

        tagname = 'NUMBER_OF_PROCESSORS_PER_DIAGONALIZATION'
        parsed_data[tagname.lower().replace('-', '_')] = parse_xml_child_integer(tagname, target_tags)
    except:
        pass

    # CARD TIMESTEPS

    cardname = 'TIMESTEPS'
    try:
        target_tags = read_xml_card(dom, cardname)
    except Exception as e:
        print(e)


    for tagname in ['STEP0', 'STEPM']:
        try:
            tag = target_tags.getElementsByTagName(tagname)[0]

            try:
                second_tagname = 'ACCUMULATORS'
                second_tag = tag.getElementsByTagName(second_tagname)[0]
                data = second_tag.childNodes[0].data.rstrip().split()  # list of floats
                parsed_data[second_tagname.replace('-', '_').lower()] = [float(i) for i in data]
            except:
                pass

            second_tagname = 'IONS_POSITIONS'
            second_tag = tag.getElementsByTagName(second_tagname)[0]
            third_tagname = 'stau'
            third_tag = second_tag.getElementsByTagName(third_tagname)[0]
            list_data = third_tag.childNodes[0].data.rstrip().split()
            list_data = [float(i) for i in list_data]
            # convert to matrix
            val = []
            mat = []
            for i, data in enumerate(list_data):
                val.append(data)
                if (i + 1) % 3 == 0:
                    mat.append(val)
                    val = []
            parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            third_tagname = 'svel'
            third_tag = second_tag.getElementsByTagName(third_tagname)[0]
            list_data = third_tag.childNodes[0].data.rstrip().split()
            list_data = [float(i) for i in list_data]
            # convert to matrix
            val = []
            mat = []
            for i, data in enumerate(list_data):
                val.append(data)
                if (i + 1) % 3 == 0:
                    mat.append(val)
                    val = []
            parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            try:
                third_tagname = 'taui'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]
                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass

            try:
                third_tagname = 'cdmi'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                            ] = [float(i) for i in list_data]
            except:
                pass

            try:
                third_tagname = 'force'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]
                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass

            second_tagname = 'IONS_NOSE'
            second_tag = tag.getElementsByTagName(second_tagname)[0]
            third_tagname = 'nhpcl'
            third_tag = second_tag.getElementsByTagName(third_tagname)[0]
            parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                        ] = float(third_tag.childNodes[0].data)
            third_tagname = 'nhpdim'
            third_tag = second_tag.getElementsByTagName(third_tagname)[0]
            parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                        ] = float(third_tag.childNodes[0].data)
            third_tagname = 'xnhp'
            third_tag = second_tag.getElementsByTagName(third_tagname)[0]
            parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                        ] = float(third_tag.childNodes[0].data)
            try:
                third_tagname = 'vnhp'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                            ] = float(third_tag.childNodes[0].data)
            except:
                pass

            try:
                second_tagname = 'ekincm'
                second_tag = tag.getElementsByTagName(second_tagname)[0]
                parsed_data[second_tagname.replace('-', '_').lower()] = float(second_tag.childNodes[0].data)
            except:
                pass

            second_tagname = 'ELECTRONS_NOSE'
            second_tag = tag.getElementsByTagName(second_tagname)[0]
            try:
                third_tagname = 'xnhe'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                            ] = float(third_tag.childNodes[0].data)
            except:
                pass
            try:
                third_tagname = 'vnhe'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()
                            ] = float(third_tag.childNodes[0].data)
            except:
                pass

            second_tagname = 'CELL_PARAMETERS'
            second_tag = tag.getElementsByTagName(second_tagname)[0]
            try:
                third_tagname = 'ht'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]
                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass
            try:
                third_tagname = 'htvel'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]
                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass
            try:
                third_tagname = 'gvel'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]
                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass

            second_tagname = 'CELL_NOSE'
            second_tag = tag.getElementsByTagName(second_tagname)[0]
            try:
                third_tagname = 'xnhh'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]

                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass
            try:
                third_tagname = 'vnhh'
                third_tag = second_tag.getElementsByTagName(third_tagname)[0]
                list_data = third_tag.childNodes[0].data.rstrip().split()
                list_data = [float(i) for i in list_data]
                # convert to matrix
                val = []
                mat = []
                for i, data in enumerate(list_data):
                    val.append(data)
                    if (i + 1) % 3 == 0:
                        mat.append(val)
                        val = []
                parsed_data[(second_tagname + '_' + third_tagname).replace('-', '_').lower()] = mat
            except:
                pass
        except Exception as e:
            print((e, 'Error parsing CARD {}'.format(cardname)))
            #raise QEOutputParsingError('Error parsing CARD {}'.format(cardname) )

    # CARD BAND_STRUCTURE_INFO

    cardname='BAND_STRUCTURE_INFO'
    try:
        target_tags=read_xml_card(dom,cardname)
    except Exception as e:
        print(e)


    tagname='NUMBER_OF_ATOMIC_WFC'
    try:
        parsed_data[tagname.lower().replace('-','_')] = parse_xml_child_integer(tagname,target_tags)
    except Exception as e:
        print(e)


    tagname='NUMBER_OF_ELECTRONS'
    try:
        parsed_data[tagname.lower().replace('-','_')] = int(parse_xml_child_float(tagname,target_tags))
    except Exception as e:
        print(e)


    tagname='NUMBER_OF_BANDS'
    try:
        parsed_data[tagname.lower().replace('-','_')] = parse_xml_child_integer(tagname,target_tags)
    except Exception as e:
        print(e)


    tagname='NUMBER_OF_SPIN_COMPONENTS'
    try:
        parsed_data[tagname.lower().replace('-','_')] = parse_xml_child_integer(tagname,target_tags)
    except Exception as e:
        print(e)


    # TODO
    # - EIGENVALUES (that actually just contains occupations)
    #   Why should I be interested in that, if CP works for insulators only?
    # - EIGENVECTORS
    # - others TODO are written in the function

    return parsed_data
