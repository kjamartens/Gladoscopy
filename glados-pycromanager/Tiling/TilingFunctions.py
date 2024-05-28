'''
Tiling-specific Functions
'''
import numpy as np

#Obtain list of XY positions from starting conditions
def InitialiseXYPositions(sz_x,sz_y,startx,starty,mov,x_dir,y_dir,startsz,counter):
    snake = 0; #'Snake-like' behaviour for moving if wanted. Not recommended, this screws over imperfect XY stages.
    #Start a counter. Set to > 0 for initial, same-location FoVs. Normally not needed
    xy = np.empty([sz_x*sz_y+counter,2]);
    snap = np.empty([sz_x*sz_y+counter,1]);
    for i in range(0,counter):
        xy[i] = [startx, starty];

    #Add reversal to get 'snake'-like
    for yy in range(0,sz_y):
        for xx in range(0,sz_x):
            if snake:
                if (yy%2):
                    xy[counter] = [startx+mov*x_dir*(sz_x-1)+mov*xx*x_dir*-1,starty+mov*yy*y_dir];
                else:
                    xy[counter] = [startx+mov*xx*x_dir*1,starty+mov*yy*y_dir];
            else:
                xy[counter] = [startx+mov*xx*x_dir*1,starty+mov*yy*y_dir];

            snap[counter] = 1;
            if yy < startsz:
                snap[counter] = 0;
            #if yy >= sz_y-startsz:
            #    snap[counter] = 0;
            if xx < startsz:
                snap[counter] = 0;
            #if xx >= sz_x-startsz:
            #    snap[counter] = 0;
            counter = counter+1;

    return xy, snap

#Define leading zeros for file names to have 001 etc.
def getLeadingZeros(counter):
	if (counter < 10):
		lz = "00";
	else:
		if (counter < 100):
			lz = "0";
		else:
			lz = "";
	return lz;

import os
def RunStitchingAlgorithmInImageJ(x_dir,y_dir,mainFolder,daughterFolder,sztrue_x,sztrue_y,overlap):
    #Get a correct directionName based on x,y_dir
    if x_dir == 1:
        directionName = "Right & ";
    else:
        directionName = "Left & ";
    if y_dir == 1:
        directionName = directionName+"Down"
    else:
        directionName = directionName+"Up"
    if x_dir == 1 and y_dir == 1:
        directionName = directionName+"                ";
    #Create the macro text
    macroTextForStitching = "run(\"Grid/Collection stitching\", \"type=[Grid: row-by-row] order=["+directionName+"] grid_size_x="+str(sztrue_x)+" grid_size_y="+str(sztrue_y)+" tile_overlap="+str(overlap)+" first_file_index_i="+str(0)+" directory="+mainFolder+daughterFolder+"Tiling file_names=im_{iii}.tif output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] add_tiles_as_rois regression_threshold=0.3 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 add_tiles_as_rois compute_overlap display_fusion computation_parameters=[Save computation time (but use more RAM)] image_output=[Write to disk] output_directory="+mainFolder+daughterFolder+"Tiling/\");";
    #Write the macro text in the same folder
    with open(mainFolder+daughterFolder+'Tiling\Macro.ijm', 'w') as f:
        f.write(macroTextForStitching)
    #Write a BAT script that only runs headless ImageJ running this macro
    with open(mainFolder+daughterFolder+'Tiling\IJMBatMacro.bat', 'w') as f:
        f.write("c:\n");
        f.write("cd \"C:\\Users\\SMIPC2\\Documents\\Microscope Software\\Fiji.app\" \n");
        f.write("ImageJ-win64 --ij2 --headless --console --run "+mainFolder+daughterFolder+"Tiling\Macro.ijm");
    #Run the just-created bat file
    os.system(mainFolder+daughterFolder+"Tiling\IJMBatMacro.bat");
    #Afterwards, cleanup the files
    #Remove the BAT file
    os.remove(mainFolder+daughterFolder+"Tiling\IJMBatMacro.bat")
    #Remove the IJM file
    os.remove(mainFolder+daughterFolder+"Tiling\Macro.ijm")


import os
def RunRGStitchingAlgorithmInImageJ(x_dir,y_dir,mainFolder,daughterFolder,sztrue_x,sztrue_y,overlap):
    #Get a correct directionName based on x,y_dir
    if x_dir == 1:
        directionName = "Right & ";
    else:
        directionName = "Left & ";
    if y_dir == 1:
        directionName = directionName+"Down"
    else:
        directionName = directionName+"Up"
    if x_dir == 1 and y_dir == 1:
        directionName = directionName+"                ";
    #Create the macro text
    #macroTextForStitching = "run(\"Grid/Collection stitching\", \"type=[Grid: row-by-row] order=["+directionName+"] grid_size_x="+str(sztrue_x)+" grid_size_y="+str(sztrue_y)+" tile_overlap="+str(overlap)+" first_file_index_i="+str(0)+" directory="+mainFolder+daughterFolder+"Tiling/Segmented file_names=RGB_{iii}_Segment.tif output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] add_tiles_as_rois regression_threshold=0.3 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 add_tiles_as_rois compute_overlap display_fusion computation_parameters=[Save computation time (but use more RAM)] image_output=[Write to disk] output_directory="+mainFolder+daughterFolder+"Tiling/\");";

    print('Not actually copmputing overlap atm!')
    macroTextForStitching = "run(\"Grid/Collection stitching\", \"type=[Grid: row-by-row] order=["+directionName+"] grid_size_x="+str(sztrue_x)+" grid_size_y="+str(sztrue_y)+" tile_overlap="+str(overlap)+" first_file_index_i="+str(0)+" directory="+mainFolder+daughterFolder+"Tiling/Segmented file_names=RGB_{iii}_Segment.tif output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] add_tiles_as_rois regression_threshold=0.3 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 add_tiles_as_rois display_fusion computation_parameters=[Save computation time (but use more RAM)] image_output=[Write to disk] output_directory="+mainFolder+daughterFolder+"Tiling/\");";

    #Write the macro text in the same folder
    with open(mainFolder+daughterFolder+'Tiling\Macro.ijm', 'w') as f:
        f.write(macroTextForStitching)
    #Write a BAT script that only runs headless ImageJ running this macro
    with open(mainFolder+daughterFolder+'Tiling\IJMBatMacro.bat', 'w') as f:
        f.write("c:\n");
        f.write("cd \"C:\\Users\\SMIPC2\\Documents\\Microscope Software\\Fiji.app\" \n");
        f.write("ImageJ-win64 --ij2 --headless --console --run "+mainFolder+daughterFolder+"Tiling\Macro.ijm");
    #Run the just-created bat file
    os.system(mainFolder+daughterFolder+"Tiling\IJMBatMacro.bat");
    #Afterwards, cleanup the files
    #Remove the BAT file
    os.remove(mainFolder+daughterFolder+"Tiling\IJMBatMacro.bat")
    #Remove the IJM file
    #os.remove(mainFolder+daughterFolder+"Tiling\Macro.ijm")


def SegmentAllBFImages(mainFolder,daughterFolder,sztrue_x,sztrue_y):
    totNr = sztrue_x*sztrue_y
    macroText = "mainFolder = \""+mainFolder+daughterFolder+"\Tiling\";\n"+"StarDistModel = \"\\\\\\\\\\\\\\\\IFMB-NAS\\\\\\\\AG Endesfelder\\\\\\\\Data\\\\\\\\Koen\\\\\\\\Scientific\\\\\\\\Segmentation\\\\\\\\DeepBac\\\\\\\\20220914_ECHV_model.zip\";"+"""
    folder2 = mainFolder + File.separator + "Segmented";
    File.makeDirectory(folder2);\n"""+"for(i=0; i<"+str(sztrue_x*sztrue_y)+""";i++){
    	open(mainFolder+"/im_"+leftPad(i,3)+".tif");
    	run("Command From Macro", "command=[de.csbdresden.stardist.StarDist2D], args=['input':'im_"+leftPad(i,3)+".tif', 'modelChoice':'Model (.zip) from File', 'normalizeInput':'true', 'percentileBottom':'1.0', 'percentileTop':'99.8', 'probThresh':'0.4', 'nmsThresh':'0.4', 'outputType':'Both', 'modelFile':'"+StarDistModel+"', 'nTiles':'1', 'excludeBoundary':'2', 'roiPosition':'Automatic', 'verbose':'false', 'showCsbdeepProgress':'false', 'showProbAndDist':'false'], process=[false]");
    	run("Set Measurements...", "area mean standard modal min centroid center perimeter bounding fit shape feret's integrated median skewness kurtosis area_fraction stack redirect=None decimal=5");
    	if (roiManager("count") > 0){
		    ROIlength = roiManager("count");
            //Removed per-image-results, because this is taken over after the combination.
    		//roiManager("multi-measure measure_all");
    		//saveAs("Results", mainFolder+"/Segmented/im_"+leftPad(i,3)+"_ROIres.csv");
    		//closeWindowByTitle("Results");
            run("Select All");
            roiManager("Save", mainFolder+"/Segmented/im_"+leftPad(i,3)+"_ROIs.zip");
    	}else{ROIlength=0;}
    	closeWindowByTitle("ROI Manager");
    	selectWindow("Label Image");
    	run("Duplicate...", "ignore");
    	selectWindow("Label Image");
    	saveAs("Tiff", mainFolder+"/Segmented/im_"+leftPad(i,3)+"_SegmentLabel.tif");
    	selectWindow("Label Image-1");
    	run("Select None");
        if (ROIlength>0){
        	changeValues(1,ROIlength+1,ROIlength*2);
        	changeValues(ROIlength*2,ROIlength*2,255);
        }
    	run("8-bit");
    	saveAs("Tiff", mainFolder+"/Segmented/im_"+leftPad(i,3)+"_Segment.tif");
    	run("16-bit");
        run("Merge Channels...", "c1=im_"+leftPad(i,3)+".tif c2=im_"+leftPad(i,3)+"_Segment.tif create");
    	saveAs("Tiff", mainFolder+"/Segmented/RGB_"+leftPad(i,3)+"_Segment.tif");
    	close("*");
    }
    run("Quit");
    function closeWindowByTitle(title) {
            selectWindow(title);
            run("Close");
    }
    function leftPad(n, width) {
      s =""+n;
      while (lengthOf(s)<width){
          s = "0"+s;}
      return s;
    }
    """
    #Write the macro text in the same folder
    with open(mainFolder+daughterFolder+'Tiling\MacroSegment.ijm', 'w') as f:
        f.write(macroText)
    #Write a BAT script that only runs headless ImageJ running this macro
    with open(mainFolder+daughterFolder+'Tiling\IJMBatMacroSegment.bat', 'w') as f:
        f.write("c:\n");
        f.write("cd \"C:\\Users\\SMIPC2\\Documents\\Microscope Software\\Fiji.app\" \n");
        f.write("ImageJ-win64 --ij2 --console --run "+mainFolder+daughterFolder+"Tiling\MacroSegment.ijm");
    #Run the just-created bat file --headless
    os.system(mainFolder+daughterFolder+"Tiling\IJMBatMacroSegment.bat");
    #Afterwards, cleanup the files
    #Remove the BAT file
    os.remove(mainFolder+daughterFolder+"Tiling\IJMBatMacroSegment.bat")
    #Remove the IJM file
    os.remove(mainFolder+daughterFolder+"Tiling\MacroSegment.ijm")

def CombineROIsAfterStitching(mainFolder,daughterFolder,imsize,nrTiles):
    macroText = "mainPath = \""+mainFolder+daughterFolder+"""/Tiling/";
    imsize = """ + str(imsize) + """;
    nrTiles = """ + str(nrTiles) + """;
    print("\\Clear");
    //TextPath = mainPath+"/Segmented/TileConfiguration.registered.txt";
    TextPath = mainPath+"/Segmented/TileConfiguration.txt";
    ROIPath = mainPath+"/Segmented/";
    open(mainPath+"/img_t1_z1_c1");

    //Remove all ROIs before starting
    roiManager("reset");

    //Close Results window
    close("Results");

    //Maximum separation for two cells in overlapping conditions to count as overlapping
    dist_pixels_overlap = 10;

    str = File.openAsString(TextPath);
    lines=split(str,"\\n");
    Text_startListIndex = 4;
    //We have to keep track of the number of ROIs, because this will change with loading new once, and we'll use the difference in prev-now to see how many ROIs are loaded for every sub-image during stiching
    curROIlength = 0;
    //Keep track of minimum x and y offset - used for later corr
    minXoffset = 0;
    minYoffset = 0;
    //Keep track of all X,Y, positions of the stitche d images
    XYImagePosArr_X = newArray(0);
    XYImagePosArr_Y = newArray(0);
    print("Loading ROIs");
    roiManager("Show All");
    for (i=Text_startListIndex;i<nrTiles+Text_startListIndex;i++){
    	//First we get the X and Y positions (and image name)
    	output = getXYposFromLine(lines[i]);
    	imName = output[0];
    	//Change the imName
    	imName = replace(imName,"RGB","im");
    	imName = replace(imName,"_Segment","");
    	xpos = parseFloat(output[1]);
    	ypos = parseFloat(output[2]);
    	//Add them to the arrays to keep track
    	XYImagePosArr_X = Array.concat(XYImagePosArr_X,xpos);
    	XYImagePosArr_Y = Array.concat(XYImagePosArr_Y,ypos);
    	if (xpos<minXoffset){
    		minXoffset = xpos;
    	}
    	if (ypos<minYoffset){
    		minYoffset = ypos;
    	}
    	if (File.exists(ROIPath+imName+"_ROIs.zip")){
    		//Open the ROIs into the ROI manager
    		roiManager("Open", ROIPath+imName+"_ROIs.zip");
    		//Select these ROIs
    		ROIarray = sequentialArray(curROIlength,roiManager("size")-1);
    		roiManager("select",ROIarray);
    		//Remove ROIs touching edges
    		toDeleteArray = RemoveEdgeTouchingROIs(ROIarray,imsize);
    		//Move them based on xpos and ypos
    		roiManager("translate", round(xpos),round(ypos));
    		//Now actually delete edge-touching ROIs
    		if (toDeleteArray.length>0){
    			roiManager("Select", toDeleteArray);
    			roiManager("Delete");
    		}
    		//Update curROIlength
    		curROIlength = roiManager("size");
    	}
    }

    print("Removing duplicate ROIs");
    //Now check all new ROIs to all old ROIs for overlaps - do not check new vs new, as these should never be removed
    //Repeated thrice in case it's in the corner and for some reason every combination is 'bad' and removes the same one multiple times
    checkAndDeleteDuplicateROIs(XYImagePosArr_X,XYImagePosArr_Y,imsize,dist_pixels_overlap);
    checkAndDeleteDuplicateROIs(XYImagePosArr_X,XYImagePosArr_Y,imsize,dist_pixels_overlap);
    checkAndDeleteDuplicateROIs(XYImagePosArr_X,XYImagePosArr_Y,imsize,dist_pixels_overlap);

    print("Measuring ROIs");
    //Select all ROIs and move with the minimum XY offset
    ROIarray = sequentialArray(0,roiManager("size")-1);
    roiManager("select",ROIarray);
    roiManager("translate", round(minXoffset)*-1,round(minYoffset)*-1);
    //Also perform all the measurements
    run("Set Measurements...", "area mean standard modal min centroid center perimeter bounding fit shape feret's integrated median skewness kurtosis area_fraction stack redirect=None decimal=5");
    roiManager("Measure");
    //Export the roi results and quit ImageJ
    saveAs("Results", """ +"\""+ mainFolder+daughterFolder + """/Tiling/StitchedROIs.csv");
    //Export the ROIs themselves
    roiManager("Save", """ +"\""+ mainFolder+daughterFolder + """/Tiling/StichedROIs.zip");
    run("Quit");

    //Function to read the TileConfig file
    function getXYposFromLine(curLine) {
     	//print(curLine);
    	splitLine = split(curLine,";");
    	imName = splitLine[0];
    	//Remove extension
    	imName = replace(imName,".tiff","");
    	imName = replace(imName,".tif","");
    	//print(imName);
    	xypos = split(splitLine[2],",");
    	xpos = xypos[0];
    	xpos = replace(xpos," \\\\(","");
    	ypos = xypos[1];
    	ypos = replace(ypos,"\\\\)","");
    	ypos = replace(ypos," ","");
    	//print(xpos);
    	//print(ypos);
    	output = newArray(3);
    	output[0] = imName;
    	output[1] = xpos;
    	output[2] = ypos;
    	return output;
     }


    //Function to get an array with sequential integers
    function sequentialArray(startval,endval){
    	arr = newArray(endval-startval+1);
    	for(i=0;i<(endval-startval+1);i++){
    		arr[i] = startval+i;
    	}
    	return arr;
    }


    //Function to remove ROIs of cells that are present from two stitched images
    function checkAndDeleteDuplicateROIs(XYImagePosArr_X,XYImagePosArr_Y,imsize,dist_pixels_overlap){
    	//Close existing results window
    	close("Results");
    	//Check
    	run("Set Measurements...", "center redirect=None decimal=3");
    	//Measure al x,y cente pos
    	ROIarray = sequentialArray(0,roiManager("size")-1);
    	roiManager("select",ROIarray);
    	roiManager("Measure");
    	//Load resuts in array for hopefully quicker analysis?
    	newROIsXpos = newArray(nResults);
    	newROIsYpos = newArray(nResults);
    	for(c=0;c<nResults;c++){
    		newROIsXpos[c] = getResult("XM",c);
    		newROIsYpos[c] = getResult("YM",c);
    	}
    	//Make an array for all entries to delete
    	toDeleteArray = newArray(0);
    	//Now start at the final entry and compare it to the ones before this entry
    	for(c=nResults-1;c>=0;c--){
    		//First check if any is nan and remove those
    		if(isNaN(newROIsXpos[c]) | isNaN(newROIsYpos[c])){
    			toDeleteArray=Array.concat(toDeleteArray,c);
    		}else{
    			for(co=c-1;co>=0;co--){
    				dist = Math.sqrt(Math.pow(newROIsXpos[c]-newROIsXpos[co],2)+Math.pow(newROIsYpos[c]-newROIsYpos[co],2));
    				if(dist<=dist_pixels_overlap){
    					//Check to which FoV this is closer
    					FinalFoVid_c = -1;
    					FinalFoVid_co = -1;
    					minFoVnearness_c = imsize;
    					minFoVnearness_co = imsize;
    					for(fovid=0;fovid<XYImagePosArr_X.length;fovid++){
    						FoVnearness_c = Math.sqrt(Math.pow(newROIsXpos[c]-(XYImagePosArr_X[fovid]+imsize/2),2)+Math.pow(newROIsYpos[c]-(XYImagePosArr_Y[fovid]+imsize/2),2));
    						FoVnearness_co = Math.sqrt(Math.pow(newROIsXpos[co]-(XYImagePosArr_X[fovid]+imsize/2),2)+Math.pow(newROIsYpos[co]-(XYImagePosArr_Y[fovid]+imsize/2),2));
    						if(FoVnearness_c<minFoVnearness_c){
    							minFoVnearness_c=FoVnearness_c;
    							FinalFoVid_c=fovid;
    						}
    						if(FoVnearness_co<minFoVnearness_co){
    							minFoVnearness_co=FoVnearness_co;
    							FinalFoVid_co=fovid;
    						}
    					}
    					if((FinalFoVid_c >= 0) | (FinalFoVid_co >=0)){
    						if(minFoVnearness_c < minFoVnearness_co){
    							//print("Deleting "+c+" for overlap with "+co+" dist: "+dist+"Closest to FoV at pos "+newROIsXpos[FinalFoVid_c]+"|"+newROIsYpos[FinalFoVid_c]+"Removing "+co);
    							toDeleteArray=Array.concat(toDeleteArray,co);
    						}else{
    							//print("Deleting "+c+" for overlap with "+co+" dist: "+dist+"Closest to FoV at pos "+newROIsXpos[FinalFoVid_co]+"|"+newROIsYpos[FinalFoVid_co]+"Removing "+c);
    							toDeleteArray=Array.concat(toDeleteArray,c);
    						}
    					}
    					break;
    				}
    			}
    		}
    	}
    	//And actually delete them
    	print("To delete:");
    	Array.print(toDeleteArray);
    	if (toDeleteArray.length>0){
    		roiManager("Select", toDeleteArray);
    		roiManager("Delete");
    	}
    	close("Results");
    }

    function RemoveEdgeTouchingROIs(ROIarray,imsize){
    	toDeleteArray = newArray(0);
    	for(ii = 0; ii < ROIarray.length; ii++){
    		roiManager("select",ROIarray[ii]);
    		getSelectionBounds(xx, yy, width, height);
    		if((xx==-1) | ((xx+width)==(imsize+1)) | (yy==-1) | ((yy+height)==(imsize+1))){
    			//print("Touching edge! "+ROIarray[ii]+"|"+xx+"|"+yy+"|"+width+"|"+height+"|");
    			toDeleteArray=Array.concat(toDeleteArray,ROIarray[ii]);
    		}
    	}
    	return toDeleteArray;
    }
    """
    #Write the macro text in the same folder
    with open(mainFolder+daughterFolder+'Tiling\MacroROIcombine.ijm', 'w') as f:
        f.write(macroText)
    #Write a BAT script that only runs headless ImageJ running this macro
    with open(mainFolder+daughterFolder+'Tiling\IJMBatMacroROICombine.bat', 'w') as f:
        f.write("c:\n");
        f.write("cd \"C:\\Users\\SMIPC2\\Documents\\Microscope Software\\Fiji.app\" \n");
        f.write("ImageJ-win64 --ij2 --console --run "+mainFolder+daughterFolder+"Tiling\MacroROIcombine.ijm");
    #Run the just-created bat file --headless
    os.system(mainFolder+daughterFolder+"Tiling\IJMBatMacroROICombine.bat");
    #Afterwards, cleanup the files
    #Remove the BAT file
    os.remove(mainFolder+daughterFolder+"Tiling\IJMBatMacroROICombine.bat")
    #Remove the IJM file
    os.remove(mainFolder+daughterFolder+"Tiling\MacroROIcombine.ijm")

def TransformCoordinates_Registered(point_of_interest,startpos,imSize,RegistrationFileName,PixelSize,xdir,ydir):
    #t = point_of_interest;
    #point_of_interest[0] = t[1];
    #point_of_interest[1] = t[0];
    #Read the TileConfiguration.registered.txt file
    filename = RegistrationFileName#'E:/Data/Scope/Test_neverImportant/Tiling/220809_1119/Tiling/TileConfiguration.registered.txt';
    with open(filename) as f:
        lines = f.readlines()

    #We start reading the line after "# Define the image coordinates"
    for l in range (0,len(lines)):
        if lines[l].find('Define the image coordinates') > 0:
            startline = l+1;
            break;

    TileConfigXYpos = np.zeros((len(lines)-startline,2))
    for l in range(startline,len(lines)):
        startp1 = lines[l].find('; (');
        endp1 = lines[l].find(', ');
        TileConfigXYpos[l-startline,0] = lines[l][startp1+3:endp1];
        startp2 = lines[l].find(', ');
        endp2 = lines[l].find(')');
        TileConfigXYpos[l-startline,1] = lines[l][startp2+2:endp2];

    distance_to_POI = np.zeros((len(TileConfigXYpos),1));
    #Calculate distance from point of interest to corner of every image and find the minimal distance
    for l in range(0,len(TileConfigXYpos)):
        if (point_of_interest[0] > TileConfigXYpos[l,0]) and (point_of_interest[1] > TileConfigXYpos[l,1]):
            distance_to_POI[l] = np.sqrt((point_of_interest[0]-TileConfigXYpos[l,0])**2+(point_of_interest[1]-TileConfigXYpos[l,1])**2);
        else:
            distance_to_POI[l] = PixelSize*4;


    #print(np.argmin(distance_to_POI))
    #print(distance_to_POI[np.argmin(distance_to_POI)])

    corner_of_closest_image = TileConfigXYpos[np.argmin(distance_to_POI)]+[0,0];
    #print(corner_of_closest_image)

    dist_POI_to_center = point_of_interest-(corner_of_closest_image)
    #print(point_of_interest)
    #print(dist_POI_to_center)

    XYpos_to_go_to = startpos+(xdir,ydir)*(corner_of_closest_image+dist_POI_to_center)*PixelSize/1000
    #print(XYpos_to_go_to)
    return XYpos_to_go_to



#Unused function I think
import glob
import shutil
def RenameToXYZ(mainFolder,daughterFolder,sztrue_x,sztrue_y):
    storeFolder = mainFolder+daughterFolder+"/XYZname";

    #for filename in glob.glob(mainFolder+daughterFolder+"im_*.tif"):
    for counter in range(0,(sztrue_x*sztrue_y)):
        filename = mainFolder+daughterFolder+"im_"+str(getLeadingZeros(counter))+str(counter)+".tif";
        ypos = np.floor(counter/sztrue_x);
        xpos = np.mod(counter,sztrue_x);
        smallFilename = filename[1+np.max(filename.find("\\")):];
        shutil.copy(filename,mainFolder+daughterFolder+"/XYZname/Z0_X"+str(getLeadingZeros(xpos))+str(np.int(xpos))+"_Y"+str(getLeadingZeros(ypos))+str(np.int(ypos))+".tif")
        #print(str(counter)+"Xpos:"+str(xpos)+"_ypos"+str(ypos))

    #for filename in glob.glob(mainFolder+daughterFolder+"im_*.tif"):
    for counter in range(0,(sztrue_x*sztrue_y)):
        filename = mainFolder+daughterFolder+"Segmented/"+"im_"+str(getLeadingZeros(counter))+str(counter)+"_Segment.tif";
        ypos = np.floor(counter/sztrue_x);
        xpos = np.mod(counter,sztrue_x);
        smallFilename = filename[1+np.max(filename.find("\\")):];
        shutil.copy(filename,mainFolder+daughterFolder+"/XYZname/Z1_X"+str(getLeadingZeros(xpos))+str(np.int(xpos))+"_Y"+str(getLeadingZeros(ypos))+str(np.int(ypos))+".tif")
        #print(str(counter)+"Xpos:"+str(xpos)+"_ypos"+str(ypos))
