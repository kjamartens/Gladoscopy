
import json
import numpy as np
import matplotlib.pyplot as plt

#Open metadata txt as JSON
#with open('C:/Data/Koen/20220322/QD_60pctGlyc_10kdil_HiLo_15ms_230mWreadout_405_61075Emm_1/QD_60pctGlyc_10kdil_HiLo_15ms_230mWreadout_405_61075Emm_1_MMStack_Pos0_metadata.txt', 'r') as f:
#  MM_JSON = json.load(f)

with open('//Smi2pc/e/Data/Koen/20220420/QDs_40pctGly_1msStroboCenter_SingleBE_488_400mW_10msFrameTimeMM_61075_1/QDs_40pctGly_1msStroboCenter_SingleBE_488_400mW_10msFrameTimeMM_61075_1_MMStack_Pos0_metadata.txt', 'r') as f:
  MM_JSON = json.load(f)

#Get nr of frames

nrframes = int(MM_JSON['Summary']['Frames'])-1
actualms = np.zeros((nrframes,1))
actualframems = np.zeros((nrframes-1,1))
for i in range(0,nrframes):
    exec("actualms[i] = MM_JSON['FrameKey-"+str(i)+"-0-0']['ElapsedTime-ms']")
    if i > 0:
        actualframems[i-1] = actualms[i]-actualms[i-1]
#actualframems = np.zeros(nrframes-1,1)
#for i in range(0,nrframes-1):
#    actualframems = actualms[i+1]-actualms[i]

plt.hist(actualframems,bins=100)
plt.show()

print("Mean frame time: " + str(np.mean(actualframems)))
print("STD frame time: " + str(np.std(actualframems)))
