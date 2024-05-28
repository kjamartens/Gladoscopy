import csv
import numpy as np
import matplotlib.pyplot as plt
def scoreCells(mainFolder,ROImeasureCSVname,scoreSettings):
    #Read the CSV
    rows = []
    with open(mainFolder+'/'+ROImeasureCSVname, 'r') as file:
        csvreader = csv.reader(file)
        header = next(csvreader)
        for row in csvreader:
            rows.append(row)

    cellScore = np.zeros((len(rows),1));
    #Loop over the possible scoring methods
    for s in range(0,len(scoreSettings)):
        #Find the current header
        headerName = list(scoreSettings.items())[s][0];
        headerIndex = header.index(headerName);
        HistogramInfoArray = np.array(rows)[:,headerIndex].astype(np.float);

        plt.figure()
        plt.hist(HistogramInfoArray,bins=50)
        plt.show(block=False)
        #print(scoreSettings(s));
        #Loop over all rows
        for r in range(0,len(rows)):
            match scoreSettings[headerName][0]:
                case "MinMax":
                    if((float(rows[r][headerIndex]) >= float(scoreSettings[headerName][1])) and (float(rows[r][headerIndex]) <= float(scoreSettings[headerName][2]))):
                        cellScore[r] += 1;

    return cellScore
    #plt.show(block=True)

import time
mapAccuracy = 10; #Value of 10 here means that the score is calculated for every 10x10 pixel blob
def calculateFoVScore(mainFolder,ROImeasureCSVname,scorePerCell,FoVinfo):
    #mapAccuracy = 100; #Value of 10 here means that the score is calculated for every 10x10 pixel blob
    #Read the CSV
    rows = []
    with open(mainFolder+'/'+ROImeasureCSVname, 'r') as file:
        csvreader = csv.reader(file)
        header = next(csvreader)
        for row in csvreader:
            rows.append(row)

    #Loop over possible FoVs
    # We know for sure that we want to be at least FoVsize/2 (assume rectangle) to the right and down of the top-left-most cell
    # and vice-versa for the bottom-right cell - these we'll use as total limits
    # Get an array with the x,y centers of the cells:
    cellcoords = (np.array(rows)[:,header.index("XM")].astype(np.float),np.array(rows)[:,header.index("YM")].astype(np.float));
    cellcoords = np.array(cellcoords);
    if FoVinfo["Shape"]=="Rectangle":
        FoVSizeInfo = FoVinfo["Size"];
        FoV_xrange = list((np.min(cellcoords[0,:])+FoVSizeInfo[0]/2,np.max(cellcoords[0,:])-FoVSizeInfo[0]/2));
        FoV_yrange = list((np.min(cellcoords[1,:])+FoVSizeInfo[1]/2,np.max(cellcoords[1,:])-FoVSizeInfo[1]/2));
        #Floor/ceil to most conservative multiple of mapAccuracy:
        FoV_xrange[0] = np.floor(FoV_xrange[0]/mapAccuracy)*mapAccuracy;
        FoV_yrange[0] = np.floor(FoV_yrange[0]/mapAccuracy)*mapAccuracy;
        FoV_xrange[1] = np.ceil(FoV_xrange[1]/mapAccuracy)*mapAccuracy;
        FoV_yrange[1] = np.ceil(FoV_yrange[1]/mapAccuracy)*mapAccuracy;
        #Loop over all regions for which we need to calculate this value


        #FoVcenters[:][:][0] =
        #print(int(FoV_yrange[1]/mapAccuracy))
        '''
        rr = (np.arange(int(FoV_yrange[0]),int(FoV_yrange[1]),int(mapAccuracy)));
        rr = np.repeat([rr], len(cellcoords[0]), axis=0)
        cellcoordsy = np.repeat([cellcoords[1][:]], len(rr[0]), axis=0);
        ymid = rr+mapAccuracy/2;
        #If cells are in the range of this area, add their score to the running total
        cellBoolean1 = cellcoords[0][:] > xmid-FoVSizeInfo[0]/2;
        cellBoolean2 = cellcoords[0][:] < xmid+FoVSizeInfo[0]/2;
        cellBoolean3 = cellcoordsy.T > ymid-FoVSizeInfo[1]/2;
        print(cellBoolean3)
        print(len(cellBoolean3))
        print(len(cellBoolean3[0]))
        cellBoolean4 = cellcoords[1][:] < ymid+FoVSizeInfo[1]/2;
        cellsInArea = (cellBoolean1*cellBoolean2*cellBoolean3*cellBoolean4)
        FoVscore[int(xx/mapAccuracy),int(rr/mapAccuracy)] += sum(scorePerCell[cellsInArea])
        '''
        FoVscore = np.zeros((int(FoV_xrange[1]/mapAccuracy),int(FoV_yrange[1]/mapAccuracy)))
        for xx in range(int(FoV_xrange[0]),int(FoV_xrange[1]),int(mapAccuracy)):
            print("xx: "+str(xx)+" - "+str(FoV_xrange[1]));
            xmid = xx+mapAccuracy/2;
            for yy in range(int(FoV_yrange[0]),int(FoV_yrange[1]),int(mapAccuracy)):
                ymid = yy+mapAccuracy/2;
                #If cells are in the range of this area, add their score to the running total
                cellBoolean1 = cellcoords[0][:] > xmid-FoVSizeInfo[0]/2;
                cellBoolean2 = cellcoords[0][:] < xmid+FoVSizeInfo[0]/2;
                cellBoolean3 = cellcoords[1][:] > ymid-FoVSizeInfo[1]/2;
                cellBoolean4 = cellcoords[1][:] < ymid+FoVSizeInfo[1]/2;
                cellsInArea = (cellBoolean1*cellBoolean2*cellBoolean3*cellBoolean4)
                FoVscore[int(xx/mapAccuracy),int(yy/mapAccuracy)] += sum(scorePerCell[cellsInArea])

                #for c in range(0,len(scorePerCell)):
                #    if ((cellcoords[0][c] > xmid-FoVSizeInfo[0]) and (cellcoords[0][c] < xmid+FoVSizeInfo[0]) and (cellcoords[1][c] > ymid-FoVSizeInfo[1]) and (cellcoords[1][c] < ymid+FoVSizeInfo[1])):
                #        FoVscore[int(xx/mapAccuracy),int(yy/mapAccuracy)] += scorePerCell[c];
        #print(np.floor(FoV_xrange[0]/mapAccuracy)*mapAccuracy);

    #plt.figure()
    #plt.imshow(FoVscore)
    #plt.show()
    #print(cellcoords[:,0:3])
    return FoVscore

def determineFoVlist(FoVscore,nrFoVoutput,FoVbleachinfo):
    XYcoordlist = np.zeros((nrFoVoutput,2));

    if FoVbleachinfo["Shape"]=="Rectangle":
        FoVbleachSizeInfo = np.ceil(np.array(FoVbleachinfo["Size"])/mapAccuracy);

        for i in range(0,nrFoVoutput):
            #Get the best point at FoVscore
            bestFoVloc = FoVscore.argmax();
            bestFoVcoord = np.array(np.unravel_index(FoVscore.argmax(), FoVscore.shape));
            XYcoordlist[i,:] = bestFoVcoord*mapAccuracy;
            #Set that FoV to zeros
            minxpos = np.amax((0,int(bestFoVcoord[0]-FoVbleachSizeInfo[0])));
            maxxpos = np.amin((len(FoVscore),int(bestFoVcoord[0]+FoVbleachSizeInfo[0])));
            minypos = np.amax((0,int(bestFoVcoord[1]-FoVbleachSizeInfo[1])));
            maxypos = np.amin((len(FoVscore),int(bestFoVcoord[1]+FoVbleachSizeInfo[1])));

            FoVscore[minxpos:maxxpos,minypos:maxypos] = -100;

            #plt.figure()
            #plt.imshow(FoVscore)
            #plt.show()

    #print(XYcoordlist)
    return XYcoordlist
