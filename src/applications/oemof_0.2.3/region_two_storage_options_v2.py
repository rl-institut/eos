# -*- coding: utf-8 -*-

''' Example for simulating wind-pv-battery systems in regions.
    Including two storage options (short-term and long-term storage).

Usage: example_region.py [options]

Options:

  -s, --scenario=SCENARIO  The scenario name. [default: scenario]
  -c, --cost=COST          The cost scenario. [default: 1]
  -t, --tech=TECH          The tech scenario. [default: 1]
  -o, --solver=SOLVER      The solver to use. Should be one of "glpk", "cbc"

                           or "gurobi".
                           [default: cbc]
  -l, --loglevel=LOGLEVEL  Set the loglevel. Should be one of DEBUG, INFO,
                           WARNING, ERROR or CRITICAL.
                           [default: ERROR]
      --timesteps=TSTEPS   Set number of timesteps. [default: 8760]
  -h, --help               Display this help.
      --year=YEAR          Weather data year. Choose from 1998 to 2014
                           [default: 2005]
      --num-regions=NUM    Number of regions. [default: 24]
      --multi-regions=NUM  Number of regions to combine each. [default: 1]
      --costopt            Cost optimization.
      --biogas             Include biogas potential.
      --biogas-flex        Include biogas as flexible potential.
      --biogas-costopt     Also cost optimize biogas bhkw.
      --lkos               LKOS load profile
      --bdew               BDEW standard load profile h0
      --ssr=SSR            Self-sufficiency degree.
      --write-results      write results to data/scenarioname_results.csv
      --dry-run            Do nothing. Only print what would be done.

'''

###############################################################################
# imports
###############################################################################
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import numpy as np
import itertools
import logging
import csv
import pickle
import pprint as pp
from demandlib import bdew as bdew

try:
    from docopt import docopt
except ImportError:
    print("Unable to import docopt.\nIs the 'docopt' package installed?")

# Outputlib
from oemof import outputlib

# Default logger of oemof
from oemof.tools import logger

# import oemof core and solph classes to create energy system objects
import oemof.solph as solph

# import graph
import oemof.graph as graph
import networkx as nx

def initialise_energysystem(year, number_timesteps):
    """initialize the energy system
    """
    logging.info('Initialize the energy system')
    date_time_index = pd.date_range('1/1/' + year,
                                    periods=number_timesteps,
                                    freq='H')

    return solph.EnergySystem(timeindex=date_time_index)


def validate(**arguments):
    valid = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if arguments["--loglevel"] not in valid:
        exit("Invalid loglevel: " + arguments["--loglevel"])
    return arguments


def read_and_calculate_parameters(**arguments):

    ###########################################################################
    # read and calculate parameters
    ###########################################################################

    logging.info('Read and calculate parameters')

    # Read parameter csv files
    region_parameter = pd.read_csv(
        '../../scenarios/region/' + arguments['--scenario'] +
        '_region_parameter.csv',
        delimiter=',', index_col=0)

    cost_parameter = pd.read_csv(
        '../../scenarios/region/' + arguments['--scenario'] +
            '_cost_parameter_' + str(arguments['--cost']) + '.csv',
        delimiter=',', index_col=0)

    tech_parameter = pd.read_csv(
        '../../scenarios/region/' + arguments['--scenario'] +
            '_tech_parameter_' + str(arguments['--tech']) + '.csv',
        delimiter=',', index_col=0)

    data = pd.read_csv("../../data/storage_invest.csv", sep=',')
    data_weather = pd.read_csv('../../data/' + arguments['--year'] + '_feedin_8043_52279.csv', sep=',')
    if arguments['--lkos']:
        data_load = pd.read_csv('../../data/Lastprofil_LKOS_MW_1h.csv', sep=',')
        data_load = data_load['demand_el'] * 1e3  # demand in kW
    elif arguments['--bdew']:
        e_slp = bdew.ElecSlp(int(arguments['--year']))
        h0_slp_15_min = e_slp.get_profile({'h0': 1})
        h0_slp = h0_slp_15_min.resample('H').mean()
        data_load = h0_slp['h0'].reset_index(drop=True)
    else:
        data_load = data['demand_el']  # demand in kW

    # data_wind = data['wind']
    # data_pv = data['pv']
    data_wind = data_weather['wind']
    data_pv = data_weather['pv']

    # Calculate ep_costs from capex
    storage_short_capex = cost_parameter.loc['storage_short']['capex']
    storage_short_lifetime = cost_parameter.loc['storage_short']['lifetime']
    storage_short_wacc = cost_parameter.loc['storage_short']['wacc']
    storage_short_epc = storage_short_capex * (storage_short_wacc * (1 + storage_short_wacc) **
                                   storage_short_lifetime) / ((1 + storage_short_wacc) **
                                                        storage_short_lifetime - 1)

    storage_long_capex = cost_parameter.loc['storage_long']['capex']
    storage_long_lifetime = cost_parameter.loc['storage_long']['lifetime']
    storage_long_wacc = cost_parameter.loc['storage_long']['wacc']
    storage_long_epc = storage_long_capex * (storage_long_wacc * (1 + storage_long_wacc) **
                                   storage_long_lifetime) / ((1 + storage_long_wacc) **
                                                        storage_long_lifetime - 1)

    storage_power_long_capex = cost_parameter.loc['storage_power_long']['capex']
    storage_power_long_lifetime = cost_parameter.loc['storage_power_long']['lifetime']
    storage_power_long_wacc = cost_parameter.loc['storage_power_long']['wacc']
    storage_power_long_epc = storage_power_long_capex * (storage_power_long_wacc * (1 + storage_power_long_wacc) **
                                   storage_power_long_lifetime) / ((1 + storage_power_long_wacc) **
                                                        storage_power_long_lifetime - 1)

    wind_capex = cost_parameter.loc['wind']['capex']
    wind_lifetime = cost_parameter.loc['wind']['lifetime']
    wind_wacc = cost_parameter.loc['wind']['wacc']
    wind_epc = wind_capex * (wind_wacc * (1 + wind_wacc) **
                        wind_lifetime) / ((1 + wind_wacc) ** wind_lifetime - 1)

    pv_capex = cost_parameter.loc['pv']['capex']
    pv_lifetime = cost_parameter.loc['pv']['lifetime']
    pv_wacc = cost_parameter.loc['pv']['wacc']
    pv_epc = pv_capex * (pv_wacc * (1 + pv_wacc) **
                         pv_lifetime) / ((1 + pv_wacc) ** pv_lifetime - 1)

    biogas_bhkw_capex = cost_parameter.loc['biogas_bhkw']['capex']
    biogas_bhkw_lifetime = cost_parameter.loc['biogas_bhkw']['lifetime']
    biogas_bhkw_wacc = cost_parameter.loc['biogas_bhkw']['wacc']
    biogas_bhkw_epc = biogas_bhkw_capex * (biogas_bhkw_wacc * (1 + biogas_bhkw_wacc) **
                         biogas_bhkw_lifetime) / ((1 + biogas_bhkw_wacc) ** biogas_bhkw_lifetime - 1)

    print(biogas_bhkw_epc)
    # Calculate grid share
    if arguments['--ssr']:
        grid_share = 1 - float(arguments['--ssr'])

    else:
        grid_share = None

    # Define combinations of multi regions
    regions = np.arange(1, int(arguments['--num-regions']) + 1)
    if int(arguments['--multi-regions']) == 2:
        i = 1
        combinations = [0, 0, 0]
        for n in itertools.combinations(regions, int(arguments['--multi-regions'])):
            combinations = np.vstack((combinations, [i, n[0], n[1]]))
            i = i + 1
    else:
        combinations = None

    print('regions: ', regions)
    print('combinations: ', combinations)

    if int(arguments['--multi-regions']) == 2:
        loop = np.arange(1, len(combinations))
    else:
        loop = regions

    parameters = {'region_parameter': region_parameter,
                  'cost_parameter': cost_parameter,
                  'tech_parameter': tech_parameter,
                  'storage_short_epc': storage_short_epc,
                  'storage_long_epc': storage_long_epc,
                  'storage_power_long_epc': storage_power_long_epc,
                  'wind_epc': wind_epc,
                  'pv_epc': pv_epc,
                  'biogas_bhkw_epc': biogas_bhkw_epc,
                  'data': data,
                  'data_load': data_load,
                  'data_wind': data_wind,
                  'data_pv': data_pv,
                  'grid_share': grid_share,
                  'regions': regions,
                  'combinations': combinations,
                  'loop': loop,
                  }

    logging.info('Check parameters')
    print('cost parameter:\n', parameters['cost_parameter'])
    print('tech parameter:\n', parameters['tech_parameter'])

    return parameters


def create_energysystem(energysystem, parameters, loopi,
                        **arguments):

    ##########################################################################
    # Create oemof object
    ##########################################################################
    logging.info('Create oemof objects')

    # Create electricity bus for demand
    bel = solph.Bus(label='region_'+str(loopi)+'_bel')

    # Create biogas bus for biogas
    bbiogas = solph.Bus(label='region_'+str(loopi)+'_bbiogas')

    # adding the buses to the energy system
    energysystem.add(bel, bbiogas)

    # Create storage transformer object for short term storage
    energysystem.add(solph.components.GenericStorage(
        label='region_'+str(loopi)+'_bat_short',
        inputs={bel: solph.Flow(variable_costs=0)},
        outputs={bel: solph.Flow(variable_costs=0)},
        capacity_loss=parameters[
            'tech_parameter'].loc['storage_short']['cap_loss'],
        invest_relation_input_capacity=parameters[
            'tech_parameter'].loc['storage_short']['c_rate'],
        invest_relation_output_capacity=parameters[
            'tech_parameter'].loc['storage_short']['c_rate'],
        inflow_conversion_factor=parameters[
            'tech_parameter'].loc['storage_short']['eta_in'],
        outflow_conversion_factor=parameters[
            'tech_parameter'].loc['storage_short']['eta_out'],
        investment=solph.Investment(ep_costs=parameters['storage_short_epc']+parameters['cost_parameter'].loc['storage_short']['opex_fix'])))

    # Create storage transformer object for long term storage
    energysystem.add(solph.components.GenericStorage(
        label='region_'+str(loopi)+'_bat_long',
        inputs={bel: solph.Flow(variable_costs=0, investment=solph.Investment(ep_costs=parameters['storage_power_long_epc']+parameters['cost_parameter'].loc['storage_power']['opex_fix']))},
        outputs={bel: solph.Flow(variable_costs=0, investment=solph.Investment(ep_costs=0))},
        invest_relation_input_output=1,
        capacity_loss=parameters[
            'tech_parameter'].loc['storage_long']['cap_loss'],
        inflow_conversion_factor=parameters[
            'tech_parameter'].loc['storage_long']['eta_in'],
        outflow_conversion_factor=parameters[
            'tech_parameter'].loc['storage_long']['eta_out'],
        investment=solph.Investment(ep_costs=parameters['storage_long_epc']+parameters['cost_parameter'].loc['storage_long']['opex_fix'])))

    # Create commodity object for import electricity resource
    if arguments['--costopt']:
        if arguments['--ssr']:
            gridsource_nv = (float(parameters
                               ['region_parameter'].loc
                               ['annual_demand_GWh'][str(loopi)]) *
                               1e6 * parameters['grid_share'])

            energysystem.add(solph.Source(
                    label='region_'+str(loopi)+'_gridsource',
                    outputs={bel: solph.Flow(
                        nominal_value=gridsource_nv,
                        summed_max=1)}))
                        # summed_max=1,
                        # min=0.0)})
        else:
            energysystem.add(solph.Source(
                    label='region_'+str(loopi)+'_gridsource',
                    outputs={bel: solph.Flow(
                        variable_costs=parameters[
                            'cost_parameter'].loc['grid']['opex_var'])}))
                            # 'cost_parameter'].loc['grid']['opex_var'],
                            # min=0.0)})

    elif arguments['--ssr']:
        if int(arguments['--multi-regions']) == 2:

            gridsource_nv = ((float(parameters
                               ['region_parameter'].loc
                               ['annual_demand_GWh'][str(parameters
                                   ['combinations'][loopi][1])]) *
                               1e6 * parameters['grid_share']) +

                            (float(parameters
                               ['region_parameter'].loc
                               ['annual_demand_GWh'][str(parameters
                                   ['combinations'][loopi][2])]) *
                               1e6 * parameters['grid_share']))
        else:
            gridsource_nv = (float(parameters
                               ['region_parameter'].loc
                               ['annual_demand_GWh'][str(loopi)]) *
                               1e6 * parameters['grid_share'])

        energysystem.add(solph.Source(
            label='region_'+str(loopi)+'_gridsource',
            outputs={bel: solph.Flow(
                nominal_value=gridsource_nv,
                summed_max=1)}))
                # summed_min=1,
                # max=0.0001)})

    else:
        print('Something is missing')

    # Create excess component to allow overproduction
    energysystem.add(solph.Sink(label='region_'+str(loopi)+'_excess',
               inputs={bel: solph.Flow()}))

    # Create fixed source object for wind

    if arguments['--costopt']:
        energysystem.add(solph.Source(label='region_'+str(loopi)+'_wind',
                     outputs={bel: solph.Flow(
                              actual_value=parameters['data_wind'],
                              fixed=True,
                              investment=solph.Investment(
                                  ep_costs=parameters['wind_epc']+parameters['cost_parameter'].loc['wind']['opex_fix']))}))

    else:
        if int(arguments['--multi-regions']) == 2:
            wind_nv = (float(parameters['region_parameter'].
                             loc['wind_MW'][str(parameters
                                                ['combinations']
                                                [loopi][1])]) * 1e3 +

                       float(parameters['region_parameter'].
                             loc['wind_MW'][str(parameters
                                                ['combinations']
                                                [loopi][2])]) * 1e3)

        else:
            wind_nv = float(parameters['region_parameter'].
                            loc['wind_MW'][str(loopi)]) * 1e3

        energysystem.add(solph.Source(label='region_'+str(loopi)+'_wind',
                     outputs={bel: solph.Flow(
                              actual_value=parameters['data_wind'],
                              nominal_value=wind_nv,
                              fixed=True)}))

    # Create fixed source object for pv
    if arguments['--costopt']:
        energysystem.add(solph.Source(label='region_'+str(loopi)+'_pv',
                         outputs={bel: solph.Flow(
                              actual_value=parameters['data_pv'],
                              fixed=True,
                              investment=solph.Investment(
                                  ep_costs=parameters['pv_epc']+parameters['cost_parameter'].loc['pv']['opex_fix']))}))

    else:
        if int(arguments['--multi-regions']) == 2:
                pv_nv = (float(parameters['region_parameter'].
                           loc['pv_MW'][str(parameters
                                            ['combinations']
                                            [loopi][1])]) * 1e3 +

                     float(parameters['region_parameter'].
                           loc['pv_MW'][str(parameters
                                            ['combinations']
                                            [loopi][2])]) * 1e3)

        else:
            pv_nv = float(parameters['region_parameter'].
                          loc['pv_MW'][str(loopi)]) * 1e3

        energysystem.add(solph.Source(label='region_'+str(loopi)+'_pv',
                     outputs={bel: solph.Flow(
                              actual_value=parameters['data_pv'],
                              nominal_value=pv_nv,
                              fixed=True)}))

    # Create source and transformer object for biogas
    if arguments['--biogas']:

        biogas_nv = float(parameters['region_parameter'].
                            loc['biogas_GWh'][str(loopi)]) * 1e6

        energysystem.add(solph.Source(label='region_'+str(loopi)+'_rbiogas',
                outputs={bbiogas: solph.Flow(
                    nominal_value=biogas_nv,
                    summed_max=1)}))

        if arguments['--biogas-flex']:

            energysystem.add(solph.Transformer(
                    label='region_'+str(loopi)+'_biogas_bhkw',
                    inputs={bbiogas: solph.Flow()},
                    outputs={bel: solph.Flow(
                        nominal_value=biogas_nv*0.38/8760*2)},
                        # nominal_value=biogas_nv*0.38/8760*2)},
                        conversion_factors={bel: 0.38}))

        else:
            energysystem.add(solph.Transformer(
                    label='region_'+str(loopi)+'_biogas_bhkw',
                    inputs={bbiogas: solph.Flow()},
                    outputs={bel: solph.Flow(
                        nominal_value=biogas_nv*0.38/8760)},
                        # nominal_value=biogas_nv*0.38/8760*2)},
                        conversion_factors={bel: 0.38}))

    if arguments['--biogas-costopt']:

        biogas_nv = float(parameters['region_parameter'].
                            loc['biogas_GWh'][str(loopi)]) * 1e6

        energysystem.add(solph.Source(label='region_'+str(loopi)+'_rbiogas',
                outputs={bbiogas: solph.Flow(
                    nominal_value=biogas_nv,
                    variable_costs=parameters[
                         'cost_parameter'].loc['biogas_th']['opex_var'],
                    summed_max=1)}))

        energysystem.add(solph.Transformer(
                label='region_'+str(loopi)+'_biogas_bhkw',
                inputs={bbiogas: solph.Flow()},
                outputs={bel: solph.Flow(
                             variable_costs=parameters[
                                   'cost_parameter'].loc['biogas_bhkw']['opex_var'],
                             investment=solph.Investment(
                                   ep_costs=parameters['biogas_bhkw_epc']+parameters['cost_parameter'].loc['biogas_bhkw']['opex_fix']))},
                             conversion_factors={bel: 0.38}))

        # if int(arguments['--multi-regions']) == 2:
        #     biogas_nv = (float(parameters['region_parameter'].
        #                    loc['biogas_GWh'][str(parameters
        #                                     ['combinations']
        #                                     [loopi][1])]) * 1e3 +

        #              float(parameters['region_parameter'].
        #                    loc['biogas_GWh'][str(parameters
        #                                     ['combinations']
        #                                     [loopi][2])]) * 1e3)

    # Create simple sink objects for demands
    if int(arguments['--multi-regions']) == 2:
        demand_av = ((parameters['data_load'] /
                      parameters['data_load'].sum() *
                      float(parameters['region_parameter'].
                      loc['annual_demand_GWh'][str(parameters
                                                       ['combinations']
                                                       [loopi][1])]) * 1e6) +

                     (parameters['data_load'] /
                      parameters['data_load'].sum() *
                      float(parameters['region_parameter'].
                      loc['annual_demand_GWh'][str(parameters
                                                       ['combinations']
                                                       [loopi][2])]) * 1e6))

    else:
        demand_av = (parameters['data_load'] /
                     parameters['data_load'].sum() *
                     float(parameters['region_parameter'].
                     loc['annual_demand_GWh'][str(loopi)])*1e6)

    energysystem.add(solph.Sink(label='region_'+str(loopi)+'_demand',
               inputs={bel: solph.Flow(
                       actual_value=demand_av,
                       fixed=True,
                       nominal_value=1)}))

    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info('Optimise the energy system')

    om = solph.Model(energysystem)

    logging.info('Store lp-file')
    om.write('optimization_problem.lp',
             io_options={'symbolic_solver_labels': True})

    logging.info('Solve the optimization problem')
    om.solve(solver=arguments['--solver'], solve_kwargs={'tee': True})

    return energysystem, om


def get_result_dict(energysystem, om, parameters, loopi, **arguments):
    logging.info('Check the results')

    year = arguments['--year']
    results_dc = {}

    energysystem.results['main'] = outputlib.processing.results(om)
    energysystem.results['meta'] = outputlib.processing.meta_results(om)

    # Convert keys to string and print all keys
    # Collect all the flows into and out of the busses
    # string_results = outputlib.views.convert_keys_to_strings(energysystem.results['main'])
    # print(string_results.keys())

    # print(energysystem.results['meta'])

    results = energysystem.results['main']
    bel = energysystem.groups['region_'+str(loopi)+'_bel']
    demand = energysystem.groups['region_'+str(loopi)+'_demand']
    wind = energysystem.groups['region_'+str(loopi)+'_wind']
    pv = energysystem.groups['region_'+str(loopi)+'_pv']
    gridsource = energysystem.groups['region_'+str(loopi)+'_gridsource']
    excess = energysystem.groups['region_'+str(loopi)+'_excess']
    storage_short = energysystem.groups['region_'+str(loopi)+'_bat_short']
    storage_long = energysystem.groups['region_'+str(loopi)+'_bat_long']

    if (arguments['--biogas']) or (arguments['--biogas-costopt']):
        biogas_bhkw = energysystem.groups['region_'+str(loopi)+'_biogas_bhkw']


    # Installed capacities
    # --------------------------------------------------------------------------------
    storage_short_inst_cap = results[(storage_short, None)]['scalars']['invest']
    storage_long_inst_cap = results[(storage_long, None)]['scalars']['invest']

    storage_short_inst_in = results[(bel, storage_short)]['scalars']['invest']
    storage_short_inst_out = results[(storage_short, bel)]['scalars']['invest']

    storage_long_inst_in = results[(bel, storage_long)]['scalars']['invest']
    storage_long_inst_out = results[(storage_long, bel)]['scalars']['invest']

    if arguments['--costopt']:
         wind_inst = (results[wind, bel])['scalars']['invest']
         pv_inst = (results[pv, bel])['scalars']['invest']

    if arguments['--biogas-costopt']:
        biogas_bhkw_inst = results[(biogas_bhkw, bel)]['scalars']['invest']

    # --------------------------------------------------------------------------------

    # Sequences
    # --------------------------------------------------------------------------------
    demand = results[(bel, demand)]['sequences']
    wind = results[(wind, bel)]['sequences']
    pv = results[(pv, bel)]['sequences']
    gridsource = results[(gridsource, bel)]['sequences']
    excess = results[(bel, excess)]['sequences']
    storage_short_in = results[(bel, storage_short)]['sequences']
    storage_long_in = results[(bel, storage_long)]['sequences']
    storage_short_out = results[(storage_short, bel)]['sequences']
    storage_long_out = results[(storage_long, bel)]['sequences']

    if (arguments['--biogas']) or (arguments['--biogas-costopt']):
        biogas_bhkw = results[(biogas_bhkw, bel)]['sequences']

    # --------------------------------------------------------------------------------

    # Write to dictionary - Sequences and postprocessings from sequences
    # --------------------------------------------------------------------------------
    results_dc['demand_'+str(loopi)] = float(demand.sum())
    results_dc['demand_ts_'+str(loopi)] = demand
    results_dc['wind_ts_'+str(loopi)] = wind
    results_dc['pv_ts_'+str(loopi)] = pv
    results_dc['wind_max_'+str(loopi)] = float(wind.max())
    results_dc['pv_max_'+str(loopi)] = float(pv.max())
    results_dc['grid_ts_'+str(loopi)] = gridsource
    results_dc['grid_'+str(loopi)] = float(gridsource.sum())
    results_dc['check_ssr_'+str(loopi)] = 1 - (gridsource.sum() / demand.sum())
    results_dc['excess_ts_'+str(loopi)] = excess
    results_dc['excess_'+str(loopi)] = float(excess.sum())
    results_dc['storage_short_in_ts_'+str(loopi)] = storage_short_in
    results_dc['storage_long_in_ts_'+str(loopi)] = storage_long_in
    results_dc['storage_short_out_ts_'+str(loopi)] = storage_short_out
    results_dc['storage_long_out_ts_'+str(loopi)] = storage_long_out
    results_dc['storage_short_in_max_'+str(loopi)] = float(storage_short_in.max())
    results_dc['storage_long_in_max_'+str(loopi)] = float(storage_long_in.max())
    results_dc['storage_short_out_max_'+str(loopi)] = float(storage_short_out.max())
    results_dc['storage_long_out_max_'+str(loopi)] = float(storage_long_out.max())

    # Write to dictionary - Scalars
    # --------------------------------------------------------------------------------
    results_dc['storage_short_cap_'+str(loopi)] = storage_short_inst_cap
    results_dc['storage_long_cap_'+str(loopi)] = storage_long_inst_cap

    results_dc['storage_short_inst_in_'+str(loopi)] = storage_short_inst_in
    results_dc['storage_short_inst_out_'+str(loopi)] = storage_short_inst_out

    results_dc['storage_long_inst_in_'+str(loopi)] = storage_long_inst_in
    results_dc['storage_long_inst_out_'+str(loopi)] = storage_long_inst_out

    results_dc['objective'] = energysystem.results['meta']['objective']

    if arguments['--costopt']:
        results_dc['wind_inst_'+str(loopi)] = wind_inst
        results_dc['pv_inst_'+str(loopi)] = pv_inst

    if arguments['--biogas-costopt']:
        results_dc['biogas_bhkw_inst_'+str(loopi)] = biogas_bhkw_inst

    if (arguments['--biogas']) or (arguments['--biogas-costopt']):
        results_dc['biogas_bhkw_ts_'+str(loopi)] = biogas_bhkw

    # --------------------------------------------------------------------------------

    if arguments['--write-results']:
        if arguments['--ssr']:
            pickle.dump(results_dc, open('../../results/region_results_dc_' +
                arguments['--scenario'] + '_' +
                arguments['--year'] + '_' +
                arguments['--ssr'] + '_' +
                str(loopi) + '_' +
                '.p', "wb"))
        else:
            pickle.dump(results_dc, open('../../results/region_results_dc_' +
                arguments['--scenario'] + '_' +
                arguments['--year'] + '_' +
                str(loopi) + '_' +
                '.p', "wb"))

    return(results_dc)


def create_plots(energysystem, year):
    logging.info('Plot results')
    myresults = outputlib.DataFramePlot(energy_system=energysystem)
    gridsource = myresults.slice_by(obj_label='gridsource', type='input',
                                    date_from=year + '-01-01 00:00:00',
                                    date_to=year + '-12-31 23:00:00')

    imp = gridsource.sort_values(by='val', ascending=False).reset_index()

    imp.plot(linewidth=1.5)

    plt.show()


def draw_graph(grph, edge_labels=True, node_color='#AFAFAF',
               edge_color='#CFCFCF', plot=True, node_size=2000,
               with_labels=True, arrows=True, layout='neato'):
    """
    Draw a graph. This function will be removed in future versions.

    Parameters
    ----------
    grph : networkxGraph
        A graph to draw.
    edge_labels : boolean
        Use nominal values of flow as edge label
    node_color : dict or string
        Hex color code oder matplotlib color for each node. If string, all
        colors are the same.

    edge_color : string
        Hex color code oder matplotlib color for edge color.

    plot : boolean
        Show matplotlib plot.

    node_size : integer
        Size of nodes.

    with_labels : boolean
        Draw node labels.

    arrows : boolean
        Draw arrows on directed edges. Works only if an optimization_model has
        been passed.
    layout : string
        networkx graph layout, one of: neato, dot, twopi, circo, fdp, sfdp.
    """
    if type(node_color) is dict:
        node_color = [node_color.get(g, '#AFAFAF') for g in grph.nodes()]

    # set drawing options
    options = {
     'prog': 'dot',
     'with_labels': with_labels,
     'node_color': node_color,
     'edge_color': edge_color,
     'node_size': node_size,
     'arrows': arrows
    }

    # draw graph
    pos = nx.drawing.nx_agraph.graphviz_layout(grph, prog=layout)

    nx.draw(grph, pos=pos, **options)

    # add edge labels for all edges
    if edge_labels is True and plt:
        labels = nx.get_edge_attributes(grph, 'weight')
        nx.draw_networkx_edge_labels(grph, pos=pos, edge_labels=labels)

    # show output
    if plot is True:
        plt.show()


def main(**arguments):
    logger.define_logging()
    esys = initialise_energysystem(year=arguments['--year'],
                                   number_timesteps=int(
                                       arguments['--timesteps']))
    parameters = read_and_calculate_parameters(**arguments)
    for loopi in parameters['loop']:
        esys, om = create_energysystem(esys,
                                   parameters,
                                   loopi,
                                   **arguments)
        get_result_dict(esys, om, parameters, loopi, **arguments)
        # create_plots(esys, year=arguments['--year'])


    # energysystem_graph = graph.create_nx_graph(esys)
    # matplotlib.rcParams['figure.figsize'] = [10.0, 10.0]
    # draw_graph(energysystem_graph, node_size=5500,
    #             node_color={
    #                         'coal': '#0f2e2e',
    #                         'gas': '#c76c56',
    #                         'oil': '#494a19',
    #                         'lignite': '#56201d',
    #                         'bel': '#9a9da1',
    #                         'bth': '#cd3333',
    #                         'wind': '#4ca7c3',
    #                         'pv': '#ffde32',
    #                         'demand_el': '#9a9da1',
    #                         'excess_el': '#9a9da1',
    #                         'demand_th': '#cd3333',
    #                         'pp_coal': '#0f2e2e',
    #                         'pp_lig': '#56201d',
    #                         'pp_gas': '#c76c56',
    #                         'pp_oil': '#494a19',
    #                         'pp_chp': '#eeac7e',
    #                         'b_heat_source': '#cd3333',
    #                         'heat_source': '#cd3333',
    #                         'heat_pump': '#42c77a'},
    #             edge_color='#eeac7e')


if __name__ == "__main__":
    arguments = docopt(__doc__)
    print(arguments)
    if arguments["--dry-run"]:
        print("This is a dry run. Exiting before doing anything.")
        exit(0)
    arguments = validate(**arguments)
    main(**arguments)