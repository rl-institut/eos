# -*- coding: utf-8 -*-

''' Example for simulating pv-battery systems in quarters

Usage: example_quartier.py [options]

Options:

  -s, --scenario=SCENARIO  The scenario name. [default: scenario_parchim]
  -c, --cost=COST          The cost scenario. [default: 2]
  -t, --tech=TECH          The tech scenario. [default: 2]
  -n, --number=NUM         Number of run. [default: 1]
  -o, --solver=SOLVER      The solver to use. Should be one of "glpk", "cbc"
                           or "gurobi".
                           [default: cbc]
  -l, --loglevel=LOGLEVEL  Set the loglevel. Should be one of DEBUG, INFO,
                           WARNING, ERROR or CRITICAL.
                           [default: ERROR]
  -h, --help               Display this help.
      --timesteps=TSTEPS   Set number of timesteps. [default: 8760]
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
      --only-slp-h0        Use only the H0 standard load profile for all
                           households.
      --only-slp           Use all standard load profiles (H0, G0, L0).
      --include-g0-l0      Include the standard load profiles G0 and L0. The
                           loads for household buildings are chosen randomly.
      --year=YEAR          Weather data year. Choose from 1998, 2003, 2007,
                           2010-2014. [default: 2005]
      --pv-costopt         Cost optimization for pv plants.
      --feedin             Option with different pv plants (will need
                           scenario_pv.csv) and max feedin
      --ssr=SSR            Self-sufficiency degree.
      --save               Save results.
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
from demandlib import bdew as bdew
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
import sys
sys.path.append('/home/caro/rlihome/Git')
# from eos import helper_coastdat as hlp


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
    cost_parameter = pd.read_csv(
        '../../scenarios/quartier/' + arguments['--scenario'] +
            '_cost_parameter_' + str(arguments['--cost']) + '.csv',
        delimiter=';', index_col=0)

    tech_parameter = pd.read_csv(
        '../../scenarios/quartier/' + arguments['--scenario'] +
            '_tech_parameter_' + str(arguments['--tech']) + '.csv',
        delimiter=';', index_col=0)

    pv_parameter = pd.read_csv(
        '../../scenarios/quartier/' + arguments['--scenario'] + '_pv.csv',
        delimiter=';', index_col=0)

    # Electricity from grid price
    price_el = cost_parameter.loc['grid']['opex_var']
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
            hh = pickle.load(open('quartier/hh_' + arguments['--scenario'] + '_' + str(arguments['--profile']) +'.p', 'rb'))

        elif arguments['--include-g0-l0']:
            if arguments['--num-hh'] == '84':
                hh = pickle.load(open('quartier/hh_' + arguments['--scenario'] + '_random_part_84.p', 'rb'))
            elif arguments['--num-hh'] == '375':
                hh = pickle.load(open('quartier/hh_' + arguments['--scenario'] + '_random_part_375.p', 'rb'))
            elif arguments['--num-hh'] == 446:
                hh = pickle.load(open('quartier/hh_' + arguments['--scenario'] + '_random_part_446.p', "wb"))

        else:
            hh = pickle.load(open('quartier/hh_' + arguments['--scenario'] + '_' + str(arguments['--number']) + '.p', "rb"))

    elif arguments['--random-hh']:
        hh_list = range(1, 75, 1)
        hh_to_choose = np.random.choice(hh_list, int(arguments['--num-hh']))
        print(np.sort(hh_to_choose))
        hh = OrderedDict()
        for i in np.arange(int(arguments['--num-hh'])):
            hh['house_' + str(i+1)] = 'hh_' + str(hh_to_choose[i])
        pickle.dump(hh, open('quartier/hh_' + arguments['--scenario'] + '_' + str(arguments['--number']) + '.p', "wb"))


    elif arguments['--profile']:
        hh_list = range(1, 4, 1)
        hh_to_choose = np.random.choice(hh_list, int(arguments['--num-hh']))
        print(np.sort(hh_to_choose))
        hh = OrderedDict()
        for i in np.arange(int(arguments['--num-hh'])):
            hh['house_' + str(i+1)] = 'hh_' + str(hh_to_choose[i])
        # pickle.dump(hh, open('quartier/hh_' + arguments['--scenario'] + '_' + str(arguments['--profile']) + '.p', "wb"))

    else:
        hh_start = int(arguments['--start-hh'])
        hh_to_choose = np.arange(hh_start, hh_start+int(arguments['--num-hh']))
        hh = OrderedDict()
        for i in np.arange(int(arguments['--num-hh'])):
            hh['house_' + str(i+1)] = 'hh_' + str(hh_to_choose[i])

    if arguments['--include-g0-l0']:
        if arguments['--num-hh'] == '84':
            hh_list = range(1, 75, 1)
            num_hh = 53
            hh_to_choose = np.random.choice(hh_list, num_hh)
            print(np.sort(hh_to_choose))
            total_buildings = np.arange(1, 85, 1)
            business = np.array([4, 5, 23, 26, 28, 31, 35, 48, 54, 61, 62, 63,
                                 65, 67, 77, 78, 81])
            agriculture = np.array([2, 8, 9, 12, 13, 22, 24, 29, 30, 34, 37,
                                    38, 39, 59])
            household_dict = np.setdiff1d(total_buildings,
                                          np.append(business, agriculture))
            print(household_dict)
            print(household_dict.size)
            hh_random = OrderedDict()
            for i in np.arange(int(household_dict.size)):
                hh_random['house_' + str(household_dict[i])] = 'hh_' + str(hh_to_choose[i])
            # pickle.dump(hh_random, open('quartier/hh_' + arguments['--scenario'] + '_random_part_84.p', "wb"))

            # This is only a dummy dictionary for a proper object creation
            # (with the right number of households)
            hh = OrderedDict()
            for i in np.arange(int(arguments['--num-hh'])):
                hh['house_' + str(i+1)] = 'hh_' + str(i+1)

            e_slp = bdew.ElecSlp(int(arguments['--year']))
            g0_l0_slp_15_min = e_slp.get_profile({'g0': 1, 'l0': 1})
            # g0_l0_slp_15_min = e_slp.get_profile({'g0': 1296000, 'l0': 95000})
            g0_l0_slp = g0_l0_slp_15_min.resample('H').mean()

            print(g0_l0_slp)

        elif arguments['--num-hh'] == '375':
            hh_list = range(1, 75, 1)
            num_hh = 308
            hh_to_choose = np.random.choice(hh_list, num_hh)
            print(np.sort(hh_to_choose))
            total_buildings = np.arange(1, 376, 1)
            business = np.array([4, 7, 8, 12, 14, 80, 129, 133, 135, 136, 146,
                                 156, 160, 172, 173, 186, 201, 216, 251, 279,
                                 289, 291, 298, 299, 300, 304, 310, 316, 349,
                                 350, 352, 358, 359, 366])
            agriculture = np.array([2, 9, 25, 26, 27, 31, 32, 56, 58, 123, 130,
                                    131, 137, 138, 142, 143, 144, 157, 162,
                                    169, 170, 174, 183, 188, 192, 194, 217,
                                    220, 234, 243, 253, 288, 296])
            household_dict = np.setdiff1d(total_buildings,
                                          np.append(business, agriculture))
            print(household_dict)
            print(household_dict.size)
            hh_random = OrderedDict()
            for i in np.arange(int(household_dict.size)):
                hh_random['house_' + str(household_dict[i])] = 'hh_' + str(hh_to_choose[i])
            # pickle.dump(quartier/hh_random, open('hh_' + arguments['--scenario'] + '_random_part_375.p', "wb"))

            # This is only a dummy dictionary for a proper object creation
            # (with the right number of households)
            hh = OrderedDict()
            for i in np.arange(int(arguments['--num-hh'])):
                hh['house_' + str(i+1)] = 'hh_' + str(i+1)

            e_slp = bdew.ElecSlp(int(arguments['--year']))
            g0_l0_slp_15_min = e_slp.get_profile({'g0': 1, 'l0': 1})
            # g0_l0_slp_15_min = e_slp.get_profile({'g0': 1507000, 'l0': 209000})
            g0_l0_slp = g0_l0_slp_15_min.resample('H').mean()

        elif arguments['--num-hh'] == '446':
            hh_list = range(1, 75, 1)
            num_hh = 373
            hh_to_choose = np.random.choice(hh_list, num_hh)
            print(np.sort(hh_to_choose))
            total_buildings = np.arange(1, 447, 1)
            business = np.array([4, 7, 8, 12, 14, 80, 129, 133, 135, 136, 146,
                                 156, 160, 172, 173, 186, 201, 216, 251, 279,
                                 289, 291, 298, 299, 300, 304, 310, 316, 349,
                                 350, 352, 358, 359, 366, 423, 424, 431, 442])
            agriculture = np.array([2, 9, 25, 26, 27, 31, 32, 56, 58, 123, 130,
                                    131, 137, 138, 142, 143, 144, 157, 162,
                                    169, 170, 174, 183, 188, 192, 194, 217,
                                    220, 234, 243, 253, 288, 296, 407, 439])
            household_dict = np.setdiff1d(total_buildings,
                                          np.append(business, agriculture))
            print(household_dict)
            print(household_dict.size)
            hh_random = OrderedDict()
            for i in np.arange(int(household_dict.size)):
                hh_random['house_' + str(household_dict[i])] = 'hh_' + str(hh_to_choose[i])
            # pickle.dump(quartier/hh_random, open('hh_' + arguments['--scenario'] + '_random_part_446.p', "wb"))

            # This is only a dummy dictionary for a proper object creation
            # (with the right number of households)
            hh = OrderedDict()
            for i in np.arange(int(arguments['--num-hh'])):
                hh['house_' + str(i+1)] = 'hh_' + str(i+1)

            e_slp = bdew.ElecSlp(int(arguments['--year']))
            g0_l0_slp_15_min = e_slp.get_profile({'g0': 1, 'l0': 1})
            g0_l0_slp = g0_l0_slp_15_min.resample('H').mean()

    print(hh)

    # Read load data and calculate total demand
    data_load = \
        pd.read_csv(
             "../../data/quartier/example_data_load_hourly_mean_74_profiles.csv",
                 sep=",") / 1000
    if arguments['--profile'] == 'summer':
        data_load = \
            pd.read_csv(
                 "../../data/quartier/example_data_load_hourly_mean_SUMMER.csv",
                     sep=",") / 1000

    if arguments['--profile'] == 'winter':
        data_load = \
            pd.read_csv(
                     "../../data/quartier/example_data_load_hourly_mean_WINTER.csv",
                     sep=",") / 1000

    if arguments['--profile'] == 'day':
        data_load = \
            pd.read_csv(
                     "../../data/quartier/example_data_load_hourly_mean_DAY.csv",
                     sep=",") / 1000

    if arguments['--profile'] == 'night':
        data_load = \
            pd.read_csv(
                     "../../data/quartier/example_data_load_hourly_mean_NIGHT.csv",
                     sep=",") / 1000

    if arguments['--only-slp-h0']:
        e_slp = bdew.ElecSlp(int(arguments['--year']))
        h0_slp_15_min = e_slp.get_profile({'h0': 1})
        h0_slp = h0_slp_15_min.resample('H').mean()

    if arguments['--only-slp']:
        e_slp = bdew.ElecSlp(int(arguments['--year']))
        slp_15_min = e_slp.get_profile({'h0': 1, 'g0': 1, 'l0': 1})
        slp = slp_15_min.resample('H').mean()

    if arguments['--scale-dem']:

        if arguments['--include-g0-l0']:
            if arguments['--num-hh'] == '84':
                consumption_total = 1668058
            elif arguments['--num-hh'] == '375':
                consumption_total = 3389786
            elif arguments['--num-hh'] == '446':
                consumption_total = 3719347
        else:
            consumption_total = {}
            for i in np.arange(int(arguments['--num-hh'])):
                consumption_total['house_' + str(i+1)] = \
                        pv_parameter.loc['annual_demand_MWh']['pv_' + str(i+1)] * 1e3

            consumption_total = sum(consumption_total.values())

    else:
        consumption_total = {}
        for i in np.arange(int(arguments['--num-hh'])):
            consumption_total['house_' + str(i+1)] = \
                    data_load[str(hh['house_' + str(i+1)])].sum()

        consumption_total = sum(consumption_total.values())

    # Read standardized feed-in from pv
    # loc = {
    #     'tz': 'Europe/Berlin',
    #     'latitude': float(arguments['--lat']),
    #     'longitude': float(arguments['--lon'])}

    pv_generation = pd.read_csv('../../data/' + arguments['--year'] + '_feedin_8043_52279.csv', sep=',')['pv']
    # pv_generation = pd.read_csv('../data/storage_invest.csv', sep=',')['pv']

    # Calculate grid share
    if arguments['--ssr']:
        grid_share = 1 - float(arguments['--ssr'])

    else:
        grid_share = None

    parameters = {'cost_parameter': cost_parameter,
                  'tech_parameter': tech_parameter,
                  'pv_parameter': pv_parameter,
                  'price_el': price_el,
                  'max_feedin': max_feedin,
                  'opex_pv': opex_pv,
                  'opex_bat': opex_bat,
                  'storage_epc': storage_epc,
                  'pv_epc': pv_epc,
                  'data_load': data_load,
                  'grid_share': grid_share,
                  'hh': hh,
                  'consumption_total': consumption_total,
                  # 'loc': loc,
                  'pv_generation': pv_generation}

    if arguments['--only-slp-h0']:
        parameters.update({'h0_slp': h0_slp['h0']})

    if arguments['--only-slp']:
        parameters.update({'h0_slp': slp['h0'],
                           'g0_slp': slp['g0'],
                           'l0_slp': slp['l0']})

    if arguments['--include-g0-l0']:
        parameters.update({'g0_slp': g0_l0_slp['g0'],
                           'l0_slp': g0_l0_slp['l0'],
                           'hh_random': hh_random})

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
                nominal_value=parameters['consumption_total'] *
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
            inputs={bel_pv: solph.Flow(variable_costs=0)},
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

        # Create simple sink objects for demands
        if arguments['--scale-dem']:
            if arguments['--only-slp-h0']:
                solph.Sink(
                    label=house+"_demand",
                    inputs={bel_demand: solph.Flow(
                        actual_value=(parameters['h0_slp'] /
                            sum(parameters['h0_slp']) *
                                parameters['pv_parameter'].loc['annual_demand_MWh']
                                [label_pv] * 1e3),
                            fixed=True,
                            nominal_value=1)})

            elif arguments['--only-slp']:
                if parameters['pv_parameter'].loc['profile_type'][label_pv] == 4:
                    solph.Sink(
                        label=house+"_demand",
                        inputs={bel_demand: solph.Flow(
                            actual_value=(parameters['g0_slp'] /
                                sum(parameters['g0_slp']) *
                                    parameters['pv_parameter'].loc['annual_demand_MWh']
                                    [label_pv] * 1e3),
                                fixed=True,
                                nominal_value=1)})
                elif parameters['pv_parameter'].loc['profile_type'][label_pv] == 7:
                    solph.Sink(
                        label=house+"_demand",
                        inputs={bel_demand: solph.Flow(
                            actual_value=(parameters['l0_slp'] /
                                sum(parameters['l0_slp']) *
                                    parameters['pv_parameter'].loc['annual_demand_MWh']
                                    [label_pv] * 1e3),
                                fixed=True,
                                nominal_value=1)})
                else:
                    solph.Sink(
                        label=house+"_demand",
                        inputs={bel_demand: solph.Flow(
                            actual_value=(parameters['h0_slp'] /
                                sum(parameters['h0_slp']) *
                                    parameters['pv_parameter'].loc['annual_demand_MWh']
                                    [label_pv] * 1e3),
                                fixed=True,
                                nominal_value=1)})

            elif arguments['--include-g0-l0']:
                if parameters['pv_parameter'].loc['profile_type'][label_pv] == 4:
                    solph.Sink(
                        label=house+"_demand",
                        inputs={bel_demand: solph.Flow(
                            actual_value=(parameters['g0_slp'] /
                                sum(parameters['g0_slp']) *
                                    parameters['pv_parameter'].loc['annual_demand_MWh']
                                    [label_pv] * 1e3),
                                fixed=True,
                                nominal_value=1)})
                elif parameters['pv_parameter'].loc['profile_type'][label_pv] == 7:
                    solph.Sink(
                        label=house+"_demand",
                        inputs={bel_demand: solph.Flow(
                            actual_value=(parameters['l0_slp'] /
                                sum(parameters['l0_slp']) *
                                    parameters['pv_parameter'].loc['annual_demand_MWh']
                                    [label_pv] * 1e3),
                                fixed=True,
                                nominal_value=1)})
                else:
                    solph.Sink(
                        label=house+"_demand",
                        inputs={bel_demand: solph.Flow(
                            actual_value=(parameters['data_load']
                                [str(parameters['hh_random'][house])] /
                                sum(parameters['data_load']
                                    [str(parameters['hh_random'][house])]) *
                                    parameters['pv_parameter'].loc['annual_demand_MWh']
                                    [label_pv] * 1e3),
                                fixed=True,
                                nominal_value=1)})

            else:
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

    return energysystem


def optimize_energysystem(energysystem):

    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info('Optimise the energy system')

    om = solph.OperationalModel(energysystem)

#     logging.info('Store lp-file')
#     om.write('optimization_problem.lp',
#              io_options={'symbolic_solver_labels': True})
#
    logging.info('Solve the optimization problem')
    om.solve(solver=arguments['--solver'], solve_kwargs={'tee': True})

    return energysystem


def get_result_dict(energysystem, parameters, **arguments):
    logging.info('Check the results')

    year = arguments['--year']

    myresults = outputlib.DataFramePlot(energy_system=energysystem)

    grid = myresults.slice_by(obj_label='gridsource',
                              date_from=year+'-01-01 00:00:00',
                              date_to=year+'-12-31 23:00:00').reset_index(
                                                  ['bus_label', 'type', 'obj_label'],
                                                  drop=True)

    bat_input = myresults.slice_by(obj_label='bat',
                                   date_from=year+'-01-01 00:00:00',
                                   date_to=year+'-12-31 23:00:00').reset_index(
                                                  ['bus_label', 'type', 'obj_label'],
                                                  drop=True)

    bat_output = myresults.slice_by(obj_label='bat',
                                    date_from=year+'-01-01 00:00:00',
                                    date_to=year+'-12-31 23:00:00').reset_index(
                                                   ['bus_label', 'type', 'obj_label'],
                                                   drop=True)

    bat_soc = myresults.slice_by(obj_label='bat',
                                 date_from=year+'-01-01 00:00:00',
                                 date_to=year+'-12-31 23:00:00').reset_index(
                                                 ['bus_label', 'type', 'obj_label'],
                                                 drop=True)

    storage = energysystem.groups['bat']

    results_dc = {}
    demand_total = 0
    ts_demand_list = []
    ts_pv_list = []
    ts_excess_list = []
    ts_sc_list = []
    ts_feedin_list = []

    results_dc['ts_grid'] = grid
    results_dc['ts_bat_input'] = bat_input
    results_dc['ts_bat_output'] = bat_output
    results_dc['ts_bat_soc'] = bat_soc

    for house in parameters['hh']:
        demand = myresults.slice_by(obj_label=house+'_demand',
                                    date_from=year+'-01-01 00:00:00',
                                    date_to=year+'-12-31 23:00:00').reset_index(
                                            ['bus_label', 'type', 'obj_label'],
                                            drop=True)

        pv = myresults.slice_by(obj_label=house+'_pv',
                                date_from=year+'-01-01 00:00:00',
                                date_to=year+'-12-31 23:00:00').reset_index(
                                            ['bus_label', 'type', 'obj_label'],
                                            drop=True)

        excess = myresults.slice_by(obj_label=house+'_excess',
                                    date_from=year+'-01-01 00:00:00',
                                    date_to=year+'-12-31 23:00:00').reset_index(
                                            ['bus_label', 'type', 'obj_label'],
                                            drop=True)

        sc = myresults.slice_by(obj_label=house+'_sc_Transformer',
                                date_from=year+'-01-01 00:00:00',
                                date_to=year+'-12-31 23:00:00').reset_index(
                                            ['bus_label', 'type', 'obj_label'],
                                            drop=True)

        if arguments['--feedin']:
            feedin = myresults.slice_by(obj_label=house+'_feedin',
                                        date_from=year+'-01-01 00:00:00',
                                        date_to=year+'-12-31 23:00:00').reset_index(
                                            ['bus_label', 'type', 'obj_label'],
                                            drop=True)
            results_dc['feedin_'+house] = float(feedin.sum())
            results_dc['ts_feedin_'+house] = feedin
            ts_feedin_list.append(feedin)
            ts_feedin_all = pd.concat(ts_feedin_list, axis=1)
            results_dc['ts_feedin_all'] = ts_feedin_all
        else:
            results_dc['feedin_'+house] = 0

        if arguments['--pv-costopt']:
            pv_i = energysystem.groups[house+'_pv']
            pv_bel = energysystem.groups[house+'_bel_pv']
            pv_inst = energysystem.results[pv_i][pv_bel].invest
            results_dc['pv_inst_'+house] = pv_inst

        results_dc['demand_'+house] = demand.sum()
        results_dc['ts_demand_'+house] = demand
        demand_total = demand_total + demand.sum()
        results_dc['pv_'+house] = pv.sum()
        results_dc['pv_max_'+house] = pv.max()
        results_dc['ts_pv_'+house] = pv
        results_dc['excess_'+house] = excess.sum()
        results_dc['ts_excess_'+house] = excess
        results_dc['self_con_'+house] = sc.sum()
        # results_dc['check_ssr_'+house] = 1 - (grid.sum() / demand.sum())

        ts_demand_list.append(demand)
        ts_pv_list.append(pv)
        ts_excess_list.append(excess)
        ts_sc_list.append(sc)

    results_dc['grid'] = grid.sum()
    results_dc['check_ssr'] = 1 - (grid.sum() / demand_total)
    results_dc['storage_cap'] = energysystem.results[
        storage][storage].invest
    results_dc['objective'] = energysystem.results.objective

    results_dc['cost_parameter'] = parameters['cost_parameter']
    results_dc['tech_parameter'] = parameters['tech_parameter']
    results_dc['pv_parameter'] = parameters['pv_parameter']
    results_dc['hh'] = parameters['hh']

    ts_demand_all = pd.concat(ts_demand_list, axis=1)
    ts_pv_all = pd.concat(ts_pv_list, axis=1)
    ts_excess_all = pd.concat(ts_excess_list, axis=1)
    ts_sc_all = pd.concat(ts_sc_list, axis=1)

    residual = ts_demand_all.sum(axis=1) - ts_pv_all.sum(axis=1)
    positive_residual = residual.where(residual >= 0, 0)
    covered_by_pv = ts_demand_all.sum(axis=1) - positive_residual
#     fig = plt.figure()
#     plt.plot(residual)
#     plt.plot(positive_residual)
#     plt.plot(ts_demand_all.sum(axis=1))
#     plt.plot(ts_pv_all.sum(axis=1))
#     plt.plot(covered_by_pv)
#     plt.legend(['residual', 'positive_residual', 'demand', 'pv', 'covered_by_pv'])
#     plt.show()

    results_dc['check_ssr_pv'] = covered_by_pv.sum() / demand_total

    results_dc['ts_demand_all'] = ts_demand_all
    results_dc['ts_pv_all'] = ts_pv_all
    results_dc['ts_excess_all'] = ts_excess_all
    results_dc['ts_sc_all'] = ts_sc_all

    if arguments['--save']:
        if arguments['--profile']:
            pickle.dump(results_dc, open('../../results/quartier_results_' +
                        str(arguments['--num-hh']) + '_' +
                        str(arguments['--cost']) + '_' +
                        str(arguments['--tech']) + '_' +
                        str(arguments['--year']) + '_' +
                        str(arguments['--ssr']) + '_' +
                        str(arguments['--profile']) + '.p', 'wb'))

        elif arguments['--only-slp-h0']:
            pickle.dump(results_dc, open('../../results/quartier_results_' +
                        str(arguments['--num-hh']) + '_' +
                        str(arguments['--cost']) + '_' +
                        str(arguments['--tech']) + '_' +
                        str(arguments['--year']) + '_' +
                        str(arguments['--ssr']) + '_' +
                        'slp_h0' + '.p', 'wb'))

        elif arguments['--only-slp']:
            pickle.dump(results_dc, open('../../results/quartier_results_' +
                        str(arguments['--num-hh']) + '_' +
                        str(arguments['--cost']) + '_' +
                        str(arguments['--tech']) + '_' +
                        str(arguments['--year']) + '_' +
                        str(arguments['--ssr']) + '_' +
                        'slp' + '.p', 'wb'))

        elif arguments['--include-g0-l0']:
            pickle.dump(results_dc, open('../../results/quartier_results_' +
                        str(arguments['--num-hh']) + '_' +
                        str(arguments['--cost']) + '_' +
                        str(arguments['--tech']) + '_' +
                        str(arguments['--year']) + '_' +
                        str(arguments['--ssr']) + '_' +
                        'incl_g0_l0' + '.p', 'wb'))

        elif arguments['--number']:
            pickle.dump(results_dc, open('../../results/quartier_results_' +
                        str(arguments['--num-hh']) + '_' +
                        str(arguments['--cost']) + '_' +
                        str(arguments['--tech']) + '_' +
                        str(arguments['--year']) + '_' +
                        str(arguments['--ssr']) + '_' +
                        str(arguments['--number']) + '_' +
                        'random' + '.p', 'wb'))

        else:
            pickle.dump(results_dc, open('../../results/quartier_results_' +
                        str(arguments['--num-hh']) + '_' +
                        str(arguments['--cost']) + '_' +
                        str(arguments['--tech']) + '_' +
                        str(arguments['--year']) + '_' +
                        str(arguments['--ssr']) + '_' +
                        'random' + '.p', 'wb'))

    return(results_dc)


def create_plots(energysystem, year):

    logging.info('Plot results')

    cdict = {'wind': '#5b5bae',
             'pv': '#ffde32',
             'storage': '#42c77a',
             'demand': '#ce4aff',
             'excess_bel': '#555555'}

    # Plotting the input flows of the electricity bus for January
    myplot = outputlib.DataFramePlot(energy_system=energysystem)
    myplot.slice_unstacked(bus_label="bel_demand", type="input",
                           date_from=year + "-01-01 00:00:00",
                           date_to=year + "-01-31 00:00:00")
    colorlist = myplot.color_from_dict(cdict)
    myplot.plot(color=colorlist, linewidth=2, title="January 2012")
    myplot.ax.legend(loc='upper right')
    myplot.ax.set_ylabel('Power in MW')
    myplot.ax.set_xlabel('Date')
    myplot.set_datetime_ticks(date_format='%d-%m-%Y', tick_distance=24*7)

    # Plotting the output flows of the electricity bus for January
    myplot.slice_unstacked(bus_label="bel_demand", type="output")
    myplot.plot(title="Year 2016", colormap='Spectral', linewidth=2)
    myplot.ax.legend(loc='upper right')
    myplot.ax.set_ylabel('Power in MW')
    myplot.ax.set_xlabel('Date')
    myplot.set_datetime_ticks()

    plt.show()

    # Plotting a combined stacked plot
    fig = plt.figure(figsize=(24, 14))
    plt.rc('legend', **{'fontsize': 19})
    plt.rcParams.update({'font.size': 19})
    plt.style.use('grayscale')

    handles, labels = myplot.io_plot(
        bus_label='bel_demand', cdict=cdict,
        barorder=['pv', 'wind', 'storage'],
        lineorder=['demand', 'storage', 'excess_bel'],
        line_kwa={'linewidth': 4},
        ax=fig.add_subplot(1, 1, 1),
        date_from=year + "-06-01 00:00:00",
        date_to=year + "-06-8 00:00:00",
        )
    myplot.ax.set_ylabel('Power in MW')
    myplot.ax.set_xlabel('Date')
    myplot.ax.set_title("Electricity bus")
    myplot.set_datetime_ticks(tick_distance=24, date_format='%d-%m-%Y')
    myplot.outside_legend(handles=handles, labels=labels)

    plt.show()

#     gridsource = myresults.slice_by(obj_label='gridsource', type='input',
#                                     date_from=year + '-01-01 00:00:00',
#                                     date_to=year + '-12-31 23:00:00')
#
#     imp = gridsource.sort_values(by='val', ascending=False).reset_index()
#
#     imp.plot(linewidth=1.5)
#
#     plt.show()
#

def main(**arguments):
    logger.define_logging()
    esys = initialise_energysystem(year=arguments['--year'],
                                   number_timesteps=int(
                                       arguments['--timesteps']))
    parameters = read_and_calculate_parameters(**arguments)
    esys = create_energysystem(esys,
                               parameters,
                               **arguments)
    esys = optimize_energysystem(esys)
    # esys.dump()
    # esys.restore()
    import pprint as pp
    results = get_result_dict(esys, parameters, **arguments)
    print('grid: ', results['grid'])
    print('check_ssr: ', results['check_ssr'])
    print('storage_cap: ', results['storage_cap'])
    print('objective: ', results['objective'])
    print('check_ssr_pv: ', results['check_ssr_pv'])
    if arguments['--pv-costopt']:
        print('pv_inst: ', (results['pv_inst_house_1'] +
         results['pv_inst_house_2'] +
         results['pv_inst_house_3'] +
         results['pv_inst_house_4'] +
         results['pv_inst_house_5'] +
         results['pv_inst_house_6'] +
         results['pv_inst_house_7'] +
         results['pv_inst_house_8'] +
         results['pv_inst_house_9'] +
         results['pv_inst_house_10']))
    # create_plots(esys, year=arguments['--year'])


if __name__ == "__main__":
    arguments = docopt(__doc__)
    print(arguments)
    if arguments["--dry-run"]:
        print("This is a dry run. Exiting before doing anything.")
        exit(0)
    # arguments = validate(**arguments)
    main(**arguments)