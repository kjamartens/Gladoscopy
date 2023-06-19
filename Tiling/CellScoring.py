'''
Idea:  three-step process to get list of FoVs to image

1. every cell gets a score by some user-defined metric (think 'area between x and y, length no higher than z')
2. every possible FoV (with like 10x10 px resolution or so) gets a total score based on 1
3. A series of FoVs is determined from 2, taking bleached areas and buffer zones and such into account

'''
from CellScoringFunctions import *
#settings
mainFolder = 'E:/Data/Scope/Tiling/Hfx_20220810/ImSize512_Overlap20/220810_1648/Tiling';
ROImeasureCSVname = 'StitchedROIs.csv'

#First we score the individual cells
scoreSettings = {
    "Area": ('MinMax',250,550),
    "Width": ('MinMax',0,2000),
};
#'MinMax': simply only give a score of 1 to cells between this score, 0 otherwise.
scorePerCell = scoreCells(mainFolder,ROImeasureCSVname,scoreSettings)

# Now score the FoVs and create a map of this.
FoVinfo = {
    "Shape":"Rectangle",
    "Size":[512, 512],
}
FoVscore = calculateFoVScore(mainFolder,ROImeasureCSVname,scorePerCell,FoVinfo)

#Finally, we determine the best FoVs to image from this map.
FoVBleachinfo = {
    "Shape":"Rectangle",
    "Size":[512*1.5, 512*1.5],
}
XYcenterPointList = determineFoVlist(FoVscore,5,FoVBleachinfo)
