# -*- coding: utf-8 -*-

''' Example for simulating wind-pv-battery systems in regions.

Usage: example_region.py [options]

Options:

  -s, --scenario=SCENARIO  The scenario name. [default: scenario]
  -o, --solver=SOLVER      The solver to use. Should be one of "glpk", "cbc"
                           or "gurobi".
                           [default: cbc]
  -l, --loglevel=LOGLEVEL  Set the loglevel. Should be one of DEBUG, INFO,
                           WARNING, ERROR or CRITICAL.
                           [default: ERROR]
  -t, --timesteps=TSTEPS   Set number of timesteps. [default: 8760]
  -h, --help               Display this help.
      --lat=LAT            Sets the simulation longitude to choose the right
                           weather data set. [default: 53.41] # Parchim
      --lon=LON            Sets the simulation latitude to choose the right
                           weather data set. [default: 11.84] # Parchim
      --year=YEAR          Weather data year. Choose from 1998 to 2014
                           [default: 2005]
      --num-regions=NUM    Number of regions. [default: 24]
      --multi-regions=NUM  Number of regions to combine each. [default: 1]
      --costopt            Cost optimization.
      --biogas             Include biogas potential.
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


def initialise_energysystem(year, number_timesteps):
    """initialize the energy system
    """
    logging.info('Initialize the energy system')
    date_time_index = pd.date_range('1/1/' + year,
                                    periods=number_timesteps,
                                    freq='H')

    return solph.EnergySystem(groupings=solph.GROUPINGS,
                              timeindex=date_time_index)


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
        'scenarios_region/' + arguments['--scenario'] +
        '_region_parameter.csv',
        delimiter=',', index_col=0)

    cost_parameter = pd.read_csv(
        'scenarios_region/' + arguments['--scenario'] + '_cost_parameter.csv',
        delimiter=',', index_col=0)

    tech_parameter = pd.read_csv(
        'scenarios_region/' + arguments['--scenario'] + '_tech_parameter.csv',
        delimiter=',', index_col=0)

    data = pd.read_csv("../example/example_data/storage_invest.csv", sep=',')
    data_weather = pd.read_csv('../data/' + arguments['--year'] + '_feedin_8043_52279.csv', sep=',')
    if arguments['--lkos']:
        data_load = pd.read_csv('../data/Lastprofil_LKOS_MW_1h.csv', sep=',')
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
    storage_capex = cost_parameter.loc['storage']['capex']
    storage_lifetime = cost_parameter.loc['storage']['lifetime']
    storage_wacc = cost_parameter.loc['storage']['wacc']
    storage_epc = storage_capex * (storage_wacc * (1 + storage_wacc) **
                                   storage_lifetime) / ((1 + storage_wacc) **
                                                        storage_lifetime - 1)

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
                  'storage_epc': storage_epc,
                  'wind_epc': wind_epc,
                  'pv_epc': pv_epc,
                  'biogas_bhkw_epc': biogas_bhkw_epc,
                  'data': data,
                  'data_load': data_load,
                  'data_wind': data_wind,
                  'data_pv': data_pv,
                  'storage_epc': storage_epc,
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

    # Create storage transformer object for storage
    solph.Storage(
        label='region_'+str(loopi)+'_bat',
        inputs={bel: solph.Flow(variable_costs=0)},
        outputs={bel: solph.Flow(variable_costs=0)},
        capacity_loss=parameters[
            'tech_parameter'].loc['storage']['cap_loss'],
        nominal_input_capacity_ratio=parameters[
            'tech_parameter'].loc['storage']['c_rate'],
        nominal_output_capacity_ratio=parameters[
            'tech_parameter'].loc['storage']['c_rate'],
        inflow_conversion_factor=parameters[
            'tech_parameter'].loc['storage']['eta_in'],
        outflow_conversion_factor=parameters[
            'tech_parameter'].loc['storage']['eta_out'],
        fixed_costs=parameters[
            'cost_parameter'].loc['storage']['opex_fix'],
        investment=solph.Investment(ep_costs=parameters['storage_epc']))

    # Create commodity object for import electricity resource
    if arguments['--costopt']:
        if arguments['--ssr']:
            gridsource_nv = (float(parameters
                               ['region_parameter'].loc
                               ['annual_demand_GWh'][str(loopi)]) *
                               1e6 * parameters['grid_share'])

            solph.Source(
                    label='region_'+str(loopi)+'_gridsource',
                    outputs={bel: solph.Flow(
                        nominal_value=gridsource_nv,
                        summed_max=1)})
        else:
            solph.Source(
                    label='region_'+str(loopi)+'_gridsource',
                    outputs={bel: solph.Flow(
                        variable_costs=parameters[
                            'cost_parameter'].loc['grid']['opex_var'])})

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

        solph.Source(
            label='region_'+str(loopi)+'_gridsource',
            outputs={bel: solph.Flow(
                nominal_value=gridsource_nv,
                summed_max=1)})

    else:
        print('Something is missing')

    # Create excess component to allow overproduction
    solph.Sink(label='region_'+str(loopi)+'__excess',
               inputs={bel: solph.Flow()})

    # Create fixed source object for wind

    if arguments['--costopt']:
        solph.Source(label='region_'+str(loopi)+'_wind',
                     outputs={bel: solph.Flow(
                              actual_value=parameters['data_wind'],
                              fixed=True,
                              fixed_costs=parameters[
                                  'cost_parameter'].loc['wind']['opex_fix'],
                              investment=solph.Investment(
                                  ep_costs=parameters['wind_epc']))})

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

        solph.Source(label='region_'+str(loopi)+'_wind',
                     outputs={bel: solph.Flow(
                              actual_value=parameters['data_wind'],
                              nominal_value=wind_nv,
                              fixed=True)})

    # Create fixed source object for pv
    if arguments['--costopt']:
        solph.Source(label='region_'+str(loopi)+'_pv',
                         outputs={bel: solph.Flow(
                              actual_value=parameters['data_pv'],
                              fixed=True,
                              fixed_costs=parameters[
                                  'cost_parameter'].loc['pv']['opex_fix'],
                              investment=solph.Investment(
                                  ep_costs=parameters['pv_epc']))})

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

        solph.Source(label='region_'+str(loopi)+'_pv',
                     outputs={bel: solph.Flow(
                              actual_value=parameters['data_pv'],
                              nominal_value=pv_nv,
                              fixed=True)})

    # Create source and transformer object for biogas
    if arguments['--biogas']:
        biogas_nv = float(parameters['region_parameter'].
                            loc['biogas_GWh'][str(loopi)]) * 1e6

        solph.Source(label='region_'+str(loopi)+'_rbiogas',
                outputs={bbiogas: solph.Flow(
                    nominal_value=biogas_nv,
                    summed_max=1)})

        if arguments['--biogas-costopt']:
            solph.LinearTransformer(
                    label='region_'+str(loopi)+'_biogas_bhkw',
                    inputs={bbiogas: solph.Flow()},
                    outputs={bel: solph.Flow(
                                 fixed_costs=parameters[
                                       'cost_parameter'].loc['biogas_bhkw']['opex_fix'],
                                 variable_costs=parameters[
                                       'cost_parameter'].loc['biogas_bhkw']['opex_var'],
                                 investment=solph.Investment(
                                       ep_costs=parameters['biogas_bhkw_epc']))},
                                 conversion_factors={bel: 0.38})

            # if int(arguments['--multi-regions']) == 2:
            #     biogas_nv = (float(parameters['region_parameter'].
            #                    loc['biogas_GWh'][str(parameters
            #                                     ['combinations']
            #                                     [loopi][1])]) * 1e3 +

            #              float(parameters['region_parameter'].
            #                    loc['biogas_GWh'][str(parameters
            #                                     ['combinations']
            #                                     [loopi][2])]) * 1e3)

        else:
            solph.LinearTransformer(
                    label='region_'+str(loopi)+'_biogas_bhkw',
                    inputs={bbiogas: solph.Flow()},
                    outputs={bel: solph.Flow(
                        nominal_value=biogas_nv*0.38/8760)},
                        # nominal_value=biogas_nv*0.38/8760*2)},
                        conversion_factors={bel: 0.38})

            # solph.LinearTransformer(
            #         label='region_'+str(loopi)+'_biogas',
            #         inputs={bbiogas: solph.Flow()},
            #         outputs={bel: solph.Flow()})

    # if arguments['--biogas_flex']:

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

    solph.Sink(label='region_'+str(loopi)+'_demand',
               inputs={bel: solph.Flow(
                       actual_value=demand_av,
                       fixed=True,
                       nominal_value=1)})

    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info('Optimise the energy system')

    om = solph.OperationalModel(energysystem)

    logging.info('Store lp-file')
    om.write('optimization_problem.lp',
             io_options={'symbolic_solver_labels': True})

    logging.info('Solve the optimization problem')
    om.solve(solver=arguments['--solver'], solve_kwargs={'tee': True})

    return energysystem


def get_result_dict(energysystem, parameters, loopi, **arguments):
    logging.info('Check the results')

    year = arguments['--year']

    results_dc = {}
    myresults = outputlib.DataFramePlot(energy_system=energysystem)

    storage = energysystem.groups['region_'+str(loopi)+'_bat']

    demand = myresults.slice_by(obj_label='region_'+str(loopi)+'_demand',
                                date_from=year+'-01-01 00:00:00',
                                date_to=year+'-12-31 23:00:00')

    wind = myresults.slice_by(obj_label='region_'+str(loopi)+'_wind',
                              date_from=year+'-01-01 00:00:00',
                              date_to=year+'-12-31 23:00:00')

    pv = myresults.slice_by(obj_label='region_'+str(loopi)+'_pv',
                            date_from=year+'-01-01 00:00:00',
                            date_to=year+'-12-31 23:00:00')

    grid = myresults.slice_by(obj_label='region_'+str(loopi)+'_gridsource',
                              date_from=year+'-01-01 00:00:00',
                              date_to=year+'-12-31 23:00:00')

    results_dc['demand_'+str(loopi)] = float(demand.sum())
    results_dc['wind_max_'+str(loopi)] = float(wind.max())
    results_dc['pv_max_'+str(loopi)] = float(pv.max())
    results_dc['grid'+str(loopi)] = grid.sum()
    results_dc['check_ssr'+str(loopi)] = 1 - (grid.sum() / demand.sum())
    results_dc['storage_cap'+str(loopi)] = energysystem.results[
        storage][storage].invest
    results_dc['objective'] = energysystem.results.objective

    if arguments['--write-results']:
        x = list(results_dc.keys())
        y = list(results_dc.values())
        f = open(
            'data/'+arguments['--scenario']+'_results.csv',
            'w', newline='')
        w = csv.writer(f, delimiter=';')
        w.writerow(x)
        w.writerow(y)
        f.close

        pickle.dump(results_dc, open('../results/region_results_dc_' +
            arguments['--scenario'] + '_' +
            arguments['--year'] + '_' +
            arguments['--ssr'] + '_' +
            str(loopi) + '_' +
            '.p', "wb"))
    # pickle.dump(myresults, open("save_myresults.p", "wb"))

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


def main(**arguments):
    logger.define_logging()
    esys = initialise_energysystem(year=arguments['--year'],
                                   number_timesteps=int(
                                       arguments['--timesteps']))
    parameters = read_and_calculate_parameters(**arguments)
    for loopi in parameters['loop']:
        esys = create_energysystem(esys,
                                   parameters,
                                   loopi,
                                   **arguments)
        esys.dump()
        # esys.restore()
        pp.pprint(get_result_dict(esys, parameters, loopi, **arguments))
        # create_plots(esys, year=arguments['--year'])


if __name__ == "__main__":
    arguments = docopt(__doc__)
    print(arguments)
    if arguments["--dry-run"]:
        print("This is a dry run. Exiting before doing anything.")
        exit(0)
    arguments = validate(**arguments)
    main(**arguments)
