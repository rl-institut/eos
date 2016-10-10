# -*- coding: utf-8 -*-

''' Example for simulating pv-battery systems in quarters

Usage: example_quartier_10hh_11_to_20.py [options]

Options:

  -s, --scenario=SCENARIO  The scenario name. [default: scenario_parchim]
  -c, --cost=COST          The cost scenario. [default: 1]
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
      --start-hh=START     Household to start when choosing from household
                           pool. Counts a chosen number of households up
                           from start-hh, see next option.
                           [default: 1]
      --num-hh=NUM         Number of households to choose. [default: 2]
      --random-hh          Set if you want to run simulation with random
                           choice of households.
      --profile=PROFILE    Choose between summer, winter, day and night.
      --load-hh            Set if you want to load your former choice of
                           random households.
      --scale-dem          Set if you want to scale profiles from given
                           demand data.
      --year=YEAR          Weather data year. Choose from 1998, 2003, 2007,
                           2010-2014. [default: 2010]
      --pv-costopt         Cost optimization for pv plants.
      --feedin             Option with different pv plants (will need
                           scenario_pv.csv) and max feedin
      --ssr=SSR            Self-sufficiency degree.
      --dry-run            Do nothing. Only print what would be done.

'''

###############################################################################
# imports
###############################################################################
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import logging
import pickle
from collections import OrderedDict

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

# import helper to read coastdat data
from eos import helper_coastdat as hlp


def initialise_energysystem(year, number_timesteps):
    """initialize the energy system
    """
    logging.info('Initialize the energy system')
    date_time_index = pd.date_range('1/1/' + year,
                                    periods=number_timesteps,
                                    freq='H')

    return solph.EnergySystem(groupings=solph.GROUPINGS,
                              time_idx=date_time_index)


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
    cost_parameter = pd.read_csv(
        'scenarios/' + arguments['--scenario'] +
            '_cost_parameter_' + str(arguments['--cost']) + '.csv',
        delimiter=',', index_col=0)

    tech_parameter = pd.read_csv(
        'scenarios/' + arguments['--scenario'] + '_tech_parameter.csv',
        delimiter=',', index_col=0)

    pv_parameter = pd.read_csv(
        'scenarios/' + arguments['--scenario'] + '_pv.csv',
        delimiter=';', index_col=0)

    # Electricity from grid price
    price_el = cost_parameter.loc['grid']['opex_var']
    fit = cost_parameter.loc['fit']['opex_var']
    sc_tax = cost_parameter.loc['sc']['opex_var']
    opex_pv = cost_parameter.loc['pv']['opex_fix']
    opex_bat = cost_parameter.loc['storage']['opex_fix']

    max_feedin = tech_parameter.loc['pv']['max_feedin']

    # Calculate ep_costs from capex
    storage_capex = cost_parameter.loc['storage']['capex']
    storage_lifetime = cost_parameter.loc['storage']['lifetime']
    storage_wacc = cost_parameter.loc['storage']['wacc']
    storage_epc = storage_capex * (storage_wacc * (1 + storage_wacc) **
                                   storage_lifetime) / ((1 + storage_wacc) **
                                                        storage_lifetime - 1)

    pv_capex = cost_parameter.loc['pv']['capex']
    pv_lifetime = cost_parameter.loc['pv']['lifetime']
    pv_wacc = cost_parameter.loc['pv']['wacc']
    pv_epc = pv_capex * (pv_wacc * (1 + pv_wacc) **
                         pv_lifetime) / ((1 + pv_wacc) ** pv_lifetime - 1)

    # Choose households according to simulation options
    if arguments['--load-hh']:
        if arguments['--profile']:
            hh = pickle.load(open('hh_' + arguments['--scenario'] + '_' + str(arguments['--profile']) +'.p', 'rb'))

        else:
            hh = pickle.load(open('hh_' + arguments['--scenario'] + '.p', 'rb'))

    elif arguments['--random-hh']:
        hh_list = range(1, 75, 1)
        hh_to_choose = np.random.choice(hh_list, int(arguments['--num-hh']))
        print(np.sort(hh_to_choose))
        hh = OrderedDict()
        for i in np.arange(int(arguments['--num-hh'])):
            hh['house_' + str(i+1)] = 'hh_' + str(hh_to_choose[i])
        pickle.dump(hh, open('hh_' + arguments['--scenario'] + '.p', "wb"))

    elif arguments['--profile']:
        hh_list = range(1, 4, 1)
        hh_to_choose = np.random.choice(hh_list, int(arguments['--num-hh']))
        print(np.sort(hh_to_choose))
        hh = OrderedDict()
        for i in np.arange(int(arguments['--num-hh'])):
            hh['house_' + str(i+1)] = 'hh_' + str(hh_to_choose[i])
        pickle.dump(hh, open('hh_' + arguments['--scenario'] + '_' + str(arguments['--profile']) + '.p', "wb"))

    else:
        hh_start = int(arguments['--start-hh'])
        hh_to_choose = np.arange(hh_start, hh_start+int(arguments['--num-hh']))
        hh = OrderedDict()
        for i in np.arange(int(arguments['--num-hh'])):
            hh['house_' + str(i+1)] = 'hh_' + str(hh_to_choose[i])

    print(hh)

    # Read load data and calculate total demand
    data_load = \
        pd.read_csv(
             "../example/example_data/example_data_load_hourly_mean_74_profiles.csv",
                 sep=",") / 1000
    if arguments['--profile'] == 'summer':
        data_load = \
            pd.read_csv(
                 "../example/example_data/example_data_load_hourly_mean_SUMMER.csv",
                     sep=",") / 1000

    if arguments['--profile'] == 'winter':
        data_load = \
            pd.read_csv(
                     "../example/example_data/example_data_load_hourly_mean_WINTER.csv",
                     sep=",") / 1000

    if arguments['--profile'] == 'day':
        data_load = \
            pd.read_csv(
                     "../example/example_data/example_data_load_hourly_mean_DAY.csv",
                     sep=",") / 1000

    if arguments['--profile'] == 'night':
        data_load = \
            pd.read_csv(
                     "../example/example_data/example_data_load_hourly_mean_NIGHT.csv",
                     sep=",") / 1000

    if arguments['--scale-dem']:
        consumption_of_chosen_households = {}
        for i in np.arange(int(arguments['--num-hh'])):
            consumption_of_chosen_households['house_' + str(i+1)] = \
                    pv_parameter.loc['annual_demand_MWh']['pv_' + str(i+1)] * 1e3

    else:
        consumption_of_chosen_households = {}
        for i in np.arange(int(arguments['--num-hh'])):
            consumption_of_chosen_households['house_' + str(i+1)] = \
                    data_load[str(hh['house_' + str(i+1)])].sum()

    print(sum(consumption_of_chosen_households.values()))

    # Read standardized feed-in from pv
    # loc = {
    #     'tz': 'Europe/Berlin',
    #     'latitude': float(arguments['--lat']),
    #     'longitude': float(arguments['--lon'])}

    pv_generation = pd.read_csv(
              '../example/example_data/pv_generation_' + str(arguments['--year']) + '.csv', sep=",")

    pv_generation = pv_generation['pv']

    # Calculate grid share
    if arguments['--ssr']:
        grid_share = 1 - float(arguments['--ssr'])

    else:
        grid_share = None

    parameters = {'cost_parameter': cost_parameter,
                  'tech_parameter': tech_parameter,
                  'pv_parameter': pv_parameter,
                  'price_el': price_el,
                  'fit': fit,
                  'sc_tax': sc_tax,
                  'max_feedin': max_feedin,
                  'opex_pv': opex_pv,
                  'opex_bat': opex_bat,
                  'storage_epc': storage_epc,
                  'pv_epc': pv_epc,
                  'data_load': data_load,
                  'grid_share': grid_share,
                  'hh': hh,
                  'consumption_households': consumption_of_chosen_households,
                  # 'loc': loc,
                  'pv_generation': pv_generation}

    logging.info('Check parameters')
    print('cost parameter:\n', parameters['cost_parameter'])
    print('tech parameter:\n', parameters['tech_parameter'])
    print('pv parameter:\n', parameters['pv_parameter'])

    return parameters


def create_energysystem(energysystem, parameters,
                        **arguments):

    ##########################################################################
    # Create oemof object
    ##########################################################################
    logging.info('Create oemof objects')

    # Create electricity bus for demand
    bel_demand = solph.Bus(label="bel_demand")

    # Create storage transformer object for storage
    solph.Storage(
        label='bat',
        inputs={bel_demand: solph.Flow(variable_costs=0)},
        outputs={bel_demand: solph.Flow(variable_costs=0)},
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
        fixed_costs=parameters['opex_bat'],
        investment=solph.Investment(ep_costs=parameters['storage_epc']))

    # Create commodity object for import electricity resource
    if arguments['--ssr']:
        solph.Source(
            label='gridsource',
            outputs={bel_demand: solph.Flow(
                nominal_value=sum(
                    parameters['consumption_households'].values()) *
                parameters['grid_share'],
                summed_max=1)})

    else:
        solph.Source(label='gridsource', outputs={
            bel_demand: solph.Flow(
                variable_costs=parameters['price_el'])})

    house_pv = 0
    for house in parameters['hh']:
        house_pv = house_pv + 1
        label_pv = 'pv_' + str(house_pv)

        # Create electricity bus for pv
        bel_pv = solph.Bus(label=house+"_bel_pv")

        # Create excess component for bel_pv to allow overproduction
        solph.Sink(label=house+"_excess", inputs={bel_pv: solph.Flow()})

        # Create sink component for the pv feedin
        if arguments['--feedin']:
            solph.Sink(label=house+'_feedin', inputs={bel_pv: solph.Flow(
                variable_costs=parameters['fit'],
                nominal_value=parameters['pv_parameter'].loc['p_max'][label_pv],  # TODO: abhängig von PV!
                max=parameters['max_feedin'])})

        # Create linear transformer to connect pv and demand bus
        solph.LinearTransformer(
            label=house+"_sc_Transformer",
            inputs={bel_pv: solph.Flow(variable_costs=parameters['sc_tax'])},
            outputs={bel_demand: solph.Flow()},
            conversion_factors={bel_demand: 1})

        # Create fixed source object for pv
        # if arguments['--pv-costopt']:
        #     solph.Source(label=house+'_pv', outputs={bel_pv: solph.Flow(
        #         actual_value=hlp.get_pv_generation(
        #             year=int(arguments['--year']),
        #             azimuth=parameters['pv_parameter'].loc['azimuth'][label_pv],
        #             tilt=parameters['pv_parameter'].loc['tilt'][label_pv],
        #             albedo=parameters['pv_parameter'].loc['albedo'][label_pv],
        #             loc=parameters['loc']),
        #         fixed=True,
        #         fixed_costs=parameters['opex_pv'],
        #         investment=solph.Investment(ep_costs=parameters['pv_epc']))})

        if arguments['--pv-costopt']:
            solph.Source(label=house+'_pv', outputs={bel_pv: solph.Flow(
                actual_value=parameters['pv_generation'],
                fixed=True,
                fixed_costs=parameters['opex_pv'],
                investment=solph.Investment(ep_costs=parameters['pv_epc']))})

        # else:
        #     solph.Source(label=house+'_pv', outputs={bel_pv: solph.Flow(
        #         actual_value=hlp.get_pv_generation(
        #             year=int(arguments['--year']),
        #             azimuth=parameters['pv_parameter'].loc['azimuth'][label_pv],
        #             tilt=parameters['pv_parameter'].loc['tilt'][label_pv],
        #             albedo=parameters['pv_parameter'].loc['albedo'][label_pv],
        #             loc=parameters['loc']),
        #         nominal_value=parameters['pv_parameter'].loc['p_max'][label_pv],
        #         fixed=True,
        #         fixed_costs=parameters['opex_pv'])})

        else:
            solph.Source(label=house+'_pv', outputs={bel_pv: solph.Flow(
                actual_value=parameters['pv_generation'],
                nominal_value=parameters['pv_parameter'].loc['p_max'][label_pv],
                fixed=True,
                fixed_costs=parameters['opex_pv'])})
            print(parameters['pv_parameter'].loc['p_max'][label_pv])

        # Create simple sink objects for demands
        if arguments['--scale-dem']:
            solph.Sink(
                label=house+"_demand",
                inputs={bel_demand: solph.Flow(
                    actual_value=(parameters['data_load']
                        [str(parameters['hh'][house])] /
                        sum(parameters['data_load']
                            [str(parameters['hh'][house])]) *
                            parameters['pv_parameter'].loc['annual_demand_MWh']
                            [label_pv] * 1e3),
                        fixed=True,
                        nominal_value=1)})
        else:
            solph.Sink(
                label=house+"_demand",
                inputs={bel_demand: solph.Flow(
                    actual_value=parameters['data_load']
                        [str(parameters['hh'][house])],
                        fixed=True,
                        nominal_value=1)})

    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info('Optimise the energy system')

    om = solph.OperationalModel(energysystem, timeindex=energysystem.time_idx)

    logging.info('Store lp-file')
    om.write('optimization_problem.lp',
             io_options={'symbolic_solver_labels': True})

    logging.info('Solve the optimization problem')
    om.solve(solver=arguments['--solver'], solve_kwargs={'tee': True})

    return energysystem


def get_result_dict(energysystem, parameters, **arguments):
    logging.info('Check the results')

    year = arguments['--year']

    myresults = outputlib.DataFramePlot(energy_system=energysystem)

    grid = myresults.slice_by(obj_label='gridsource',
                              date_from=year+'-01-01 00:00:00',
                              date_to=year+'-12-31 23:00:00')

    bat = myresults.slice_by(obj_label='bat',
                             date_from=year+'-01-01 00:00:00',
                             date_to=year+'-12-31 23:00:00')

    storage = energysystem.groups['bat']

    results_dc = {}
    demand_total = 0

    for house in parameters['hh']:
        demand = myresults.slice_by(obj_label=house+'_demand',
                                    date_from=year+'-01-01 00:00:00',
                                    date_to=year+'-12-31 23:00:00')

        pv = myresults.slice_by(obj_label=house+'_pv',
                                date_from=year+'-01-01 00:00:00',
                                date_to=year+'-12-31 23:00:00')

        excess = myresults.slice_by(obj_label=house+'_excess',
                                    date_from=year+'-01-01 00:00:00',
                                    date_to=year+'-12-31 23:00:00')

        sc = myresults.slice_by(obj_label=house+'_sc_Transformer',
                                date_from=year+'-01-01 00:00:00',
                                date_to=year+'-12-31 23:00:00')

        if arguments['--feedin']:
            feedin = myresults.slice_by(obj_label=house+'_feedin',
                                        date_from=year+'-01-01 00:00:00',
                                        date_to=year+'-12-31 23:00:00')
            results_dc['feedin_'+house] = float(feedin.sum())
        else:
            results_dc['feedin_'+house] = 0

        if arguments['--pv-costopt']:
            pv_inst = energysystem.results[pv][pv].invest
            results_dc['pv_inst'+house] = pv_inst

        results_dc['demand_'+house] = demand.sum()
        demand_total = demand_total + demand.sum()
        results_dc['pv_'+house] = pv.sum()
        results_dc['pv_max_'+house] = pv.max()
        results_dc['excess_'+house] = excess.sum()
        results_dc['self_con_'+house] = sc.sum() / 2
        # TODO get in or oputflow of transformer
        results_dc['bat_'+house] = bat.sum()

    results_dc['grid'] = grid.sum()
    results_dc['check_ssr'] = 1 - (grid.sum() / demand_total)
    results_dc['storage_cap'] = energysystem.results[
        storage][storage].invest
    results_dc['objective'] = energysystem.results.objective

    if arguments['--profile']:
        pickle.dump(results_dc, open('../results/quartier_results_' +
                    str(arguments['--num-hh']) + '_' +
                    str(arguments['--cost']) + '_' +
                    str(arguments['--year']) + '_' +
                    str(arguments['--ssr']) + '_' +
                    str(arguments['--profile']) + '.p', 'wb'))

    else:
        pickle.dump(results_dc, open('../results/quartier_results_' +
                    str(arguments['--num-hh']) + '_' +
                    str(arguments['--cost']) + '_' +
                    str(arguments['--year']) + '_' +
                    str(arguments['--ssr']) + '_' +
                    'random' + '.p', 'wb'))

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
    esys = create_energysystem(esys,
                               parameters,
                               **arguments)
    esys.dump()
    # esys.restore()
    import pprint as pp
    results = get_result_dict(esys, parameters, **arguments)
    print('grid: ', results['grid'])
    print('check_ssr: ', results['check_ssr'])
    print('storage_cap: ', results['storage_cap'])
    print('objective: ', results['objective'])
#    create_plots(esys, year=arguments['--year'])


if __name__ == "__main__":
    arguments = docopt(__doc__)
    print(arguments)
    if arguments["--dry-run"]:
        print("This is a dry run. Exiting before doing anything.")
        exit(0)
    arguments = validate(**arguments)
    main(**arguments)
