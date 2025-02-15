# Modules used to run Differential-Privacy Pipeline
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import h3
   
def spatioTemporalGeneralization(dataframe, configFile):
    # separating latitude and longitude from location
    lat_lon = dataframe[configFile['locationCol']]
    split_lat_lon = lat_lon.astype(str).str.strip('[]').str.split(', ')
    lon = split_lat_lon.apply(lambda x: x[0])
    lat = split_lat_lon.apply(lambda x: x[1])

    #assigning h3 index to the latitude and longitude coordinates in separate dataframe  
    dfLen = len(dataframe)
    h3index = [None] * dfLen
    resolution = configFile["h3Resolution"]
    for i in range(dfLen):
        h3index[i] = h3.geo_to_h3(lat=float(lat[i]), lng=float(lon[i]), resolution=resolution)
    dataframe["h3index"] = h3index

    # assigning date and time to separate dataframe and creating a timeslot column
    dataframe["Date"] = pd.to_datetime(dataframe[configFile["datetimeCol"]]).dt.date
    dataframe["Time"] = pd.to_datetime(dataframe[configFile["datetimeCol"]]).dt.time
    time = dataframe["Time"]
    dataframe["Timeslot"] = time.apply(lambda x: x.hour)

    # assigning HATs from H3index and timeslot
    dataframe["HAT"] = ( dataframe["Timeslot"].astype(str) + " " + dataframe["h3index"])
    print('\nNumber of unique HATs created is: ' + str(dataframe['HAT'].nunique()))

    # Filtering time slots by start and end time from config file
    startTime = configFile["startTime"]
    endTime = configFile["endTime"]
    groupByColumn = 'license_plate'
    dataframe = dataframe[(dataframe["Timeslot"] >= startTime) & (dataframe["Timeslot"] <= endTime) ]

    # Selecting h3 indices where a min number of events occur in all timeslots of the day
    df1 = (dataframe.groupby(["HAT", "Date"]).agg({groupByColumn: "nunique"}).reset_index())
    df2 = df1.groupby(["HAT"]).agg({groupByColumn: "sum"}).reset_index()

    # //TODO move filtering to post aggregation as per test file 
    
    #filtering average num of occurences per day per HAT
    # date = dataframe["Date"].unique()
    # minEventOccurencesPerDay = int(configFile["minEventOccurences"])
    # limit = len(date) * minEventOccurencesPerDay
    # df3 = df2[df2[groupByColumn] >= limit]
    # df = dataframe["HAT"].isin(df3["HAT"])
    # dataframe = dataframe[df]

    # print('Number of unique HATs left after filtering is: ' + str(dataframe['HAT'].nunique()))

    return dataframe

def timeRange(dataframe):
    #calculating the number of days in the dataset
    startDay = dataframe['Date'].min()
    endDay = dataframe['Date'].max()
    timeRange = 1 + (endDay - startDay).days
    return timeRange

def aggregator(dataframe, configDict):
    #initializing variables from config file
    groupByCol = configDict['groupByCol']
    localityFactor = configDict['localityFactor']
    winsorizeLower = configDict['winsorizeLowerBound']
    winsorizeUpper = configDict['winsorizeUpperBound']
    dfThreshold = dataframe

    #winsorizing the values of the chosen column
    lowClip = dfThreshold[groupByCol].quantile(winsorizeLower) * (1 -   localityFactor)
    highClip = dfThreshold[groupByCol].quantile(winsorizeUpper) * (1 + localityFactor)
    dfThreshold[groupByCol].clip(lower=lowClip, upper=highClip, inplace = True)
        
    if (dfThreshold[groupByCol].dtype) == int or (dfThreshold[groupByCol].dtype) == float:
        dfGrouped = dfThreshold.groupby(['HAT','Date','license_plate']).agg(
                                count=(groupByCol,'count'),
                                sum=(groupByCol,'sum'),
                                max=(groupByCol,'max'),
                                min=(groupByCol,'min')).reset_index()
        
        # //TODO check mean compute with secureEnclaveTesting
        # dfGrouped['mean'] = np.round((dfGrouped['sum']/dfGrouped['count']), 2)

        # //TODO moving to post filtering
        # dfSensitivity = dfGrouped.groupby(['HAT', 'license_plate', 'Date']).agg({'count': ['count']})
        # dfSensitivity.columns = dfSensitivity.columns.droplevel(0)
        # dfSensitivity.reset_index(inplace = True)

        # dfCount = dfSensitivity.groupby(['HAT']).agg(
        #                         max_count=('count', 'max'),
        #                         sum_count=('count', 'sum'))
        # dfCount.reset_index(inplace = True)
        # print('dfCount', len(dfCount))

        #filtering average num of occurences per day per HAT
        date = dfGrouped["Date"].unique()
        minEventOccurencesPerDay = int(configDict["minEventOccurences"])
        limit = len(date) * minEventOccurencesPerDay
        dfFiltered = dfGrouped.groupby(['HAT', 'Date']).agg({'license_plate':'nunique'}).reset_index()
        # //TODO license_plate to be replaced with generic input from the config file
        dfFiltered = dfFiltered.groupby(['HAT']).agg({'license_plate':'sum'}).reset_index()
        dfFiltered.rename(columns={"license_plate": "license_plate_count"}, inplace=True)
        dfFiltered = dfFiltered[dfFiltered['license_plate_count'] >= limit]
        dfFiltered = dfGrouped["HAT"].isin(dfFiltered["HAT"])
        dfGrouped = dfGrouped[dfFiltered]
        # dfFinalGrouped.to_csv('groupingTestMultiple.csv')
        print('Number of unique HATs left after filtering is: ' + str(dfGrouped['HAT'].nunique()))
        print('########################################################################################')
        print('dfFinal Grouped after filtering', dfGrouped)

        dfSensitivity = dfGrouped.groupby(['HAT', 'license_plate', 'Date']).agg({'count': ['count']})
        dfSensitivity.columns = dfSensitivity.columns.droplevel(0)
        dfSensitivity.reset_index(inplace = True)

        dfCount = dfSensitivity.groupby(['HAT']).agg(
                                max_count=('count', 'max'),
                                sum_count=('count', 'sum'))
        dfCount.reset_index(inplace = True)
        print('dfCount', len(dfCount))

    else:
        dfGrouped = dfThreshold.groupby(['HAT']).agg(
                                count=(groupByCol,'count'))
        print('Warning: Only the count query is available for non-numeric choice of groupByCol')

    return dfGrouped, dfSensitivity, dfCount

def ITMSQuery1(dataframe):
    #average speed of buses passing through a HAT

    dfITMSQuery1 = dataframe
    #weighted mean
    dfITMSQuery1HATSum = dfITMSQuery1.groupby('HAT').agg({'sum':'sum'})
    dfITMSQuery1HATCount = dfITMSQuery1.groupby('HAT').agg({'count':'sum'})
    dfITMSQuery1 = dfITMSQuery1HATSum['sum']/dfITMSQuery1HATCount['count']
    dfITMSQuery1 = dfITMSQuery1.to_frame().reset_index()
    dfITMSQuery1.rename(columns = {0:'queryOutput'}, inplace = True)
    return dfITMSQuery1

def ITMSQuery2(dataframe, configDict):
    #average number of speed violations per HAT over all days

    #dropping all records lower than the chosen speedLimit
    speedThreshold = configDict['trueValueThreshold']

    # dropping all rows that don't meet threshold requirement
    dfITMSQuery2 = dataframe[(dataframe['max'] >= speedThreshold)].reset_index()

    # finding number of threshold violations per HAT, per Day, per license plate
    dfITMSQuery2 = dfITMSQuery2.groupby(['HAT', 'Date']).agg({'license_plate':'count'}).reset_index()

    # finding average number of violations per HAT over all the days
    dfITMSQuery2 = dfITMSQuery2.groupby(['HAT']).agg({'license_plate':'mean'}).reset_index()
    dfITMSQuery2.rename(columns={'license_plate':'queryOutput'}, inplace = True)
    return dfITMSQuery2

def NCompute(dataframe):
    #N is sum of number of unique license plates per HAT
    dataframe = dataframe.groupby(['HAT', 'Date']).agg({'license_plate':'nunique'}).reset_index()
    dataframe = dataframe.groupby(['HAT']).agg({'license_plate':'sum'}).reset_index()
    dataframe.rename(columns={'license_plate':'N'}, inplace = True)
    dfN = dataframe
    # print(dfN)
    #since 'n' is the denominator in sensitivity, max change in sensitivity is from min value of 'n'
    N = dataframe['N'].min()
    return N, dfN

def KCompute(dataframe):
    #finding 'K', the maximum number of HATs a bus passes through per day
    dfK = dataframe.groupby(['Date','license_plate']).agg({'HAT':'nunique'}).reset_index()
    K = dfK['HAT'].max()
    return K

def sensitivityComputeITMSQuery(configDict, timeRange, dfCount):
    maxValue = configDict['globalMaxValue']
    minValue = configDict['globalMinValue']

    # sensitivity for weighted query 1
    sensitivityITMSQuery1 = ((dfCount['max_count']*(maxValue - minValue))/(dfCount['sum_count']))

    # sensitivity for query 2
    # sensitivity is computed per day, number of violations per HAT can only change by 1, so max change per day is 1/no. of days
    sensitivityITMSQuery2 = 1/timeRange

    return sensitivityITMSQuery1, sensitivityITMSQuery2

def noiseComputeITMSQuery(dfITMSQuery1, dfITMSQuery2, sensitivityITMSQuery1, sensitivityITMSQuery2, configDict, K):
    dfNoiseITMSQuery1 = dfITMSQuery1
    dfNoiseITMSQuery2 = dfITMSQuery2

    # epsilon
    privacyLossBudgetEpsITMSQuery1 = configDict['privacyLossBudgetEpsQuery'][0]
    privacyLossBudgetEpsITMSQuery2 = configDict['privacyLossBudgetEpsQuery'][1]

    # computing epsilon prime
    epsPrimeQuery1 = privacyLossBudgetEpsITMSQuery1/K
    epsPrimeQuery2 = privacyLossBudgetEpsITMSQuery2/K

    # computing noise weighted query 1
    bITMSQuery1 = sensitivityITMSQuery1/epsPrimeQuery1
    noiseITMSQuery1 = np.random.laplace(0, bITMSQuery1)
    
    # computing noise query 2
    bITMSQuery2 = sensitivityITMSQuery2/epsPrimeQuery2
    noiseITMSQuery2 = np.random.laplace(0, bITMSQuery2, len(dfNoiseITMSQuery2))

    # adding noise to the true value
    dfNoiseITMSQuery1['queryNoisyOutput'] = dfNoiseITMSQuery1['queryOutput'] + noiseITMSQuery1
    dfNoiseITMSQuery2['queryNoisyOutput'] = dfNoiseITMSQuery2['queryOutput'] + noiseITMSQuery2
    # dfNoiseITMSQuery1Weighted['queryNoisyOutput'] = dfNoiseITMSQuery1Weighted['queryOutput'] + noiseITMSQuery1Weighted

    return dfNoiseITMSQuery1, dfNoiseITMSQuery2

