from pycromanager import Dataset

##TODO: your dataset path here
dataset_dir = 'E:/Data/Scope/Test_neverImportant/Tiling/acquisition_name_27'

# open the dataset
dataset = Dataset(dataset_dir)
# open the data as one big array (with an axis corresponding to xy position)
data = dataset.as_array()
# print the names of the axes
print(dataset.axes.keys())
# show general information about the data
print(data)
data
