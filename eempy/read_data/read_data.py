"""
Functions for importing raw EEM data
Author: Yongmin Hu (yongminhu@outlook.com)
Last update: 2024-01-15
"""

import os
import re
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Union, Tuple, List
from eempy.eem_processing import eem_interpolation, process_eem_stack
from scipy.interpolate import interp1d


def read_eem(file_path: str, index_pos: Union[Tuple, List, None] = None, data_format: str = 'aqualog'):
    """
    Import EEM from file. Due to the differences between EEM files generated by different instruments, the type of
    data_format must be specified. The current version only supports importing Aqualog (HORIBA) files,
    which are named using the format "xxPEM.dat" by default. The blank file generate by aqualog ('xxBEM.dat') can
    also be read with this function.

    Parameters
    ----------
    file_path: str
        The filepath to the aqualog EEM file.
    index_pos: None or tuple with two elements
        The starting and ending positions of index in filenames. For example, if you want to read the index "2024_01_01"
        from the file with the name "EEM_2024_01_01_PEM.dat", a tuple (4, 13) should be passed to this parameter.
    data_format: str
        Specify the type of EEM data format.

    Returns
    -------
    intensity: np.ndarray (2d)
        The EEM.
    ex_range: np.ndarray (1d)
        The excitation wavelengths.
    em_range: np.ndarray (1d)
        The emission wavelengths.
    index: str
        The index of the EEM.
    """
    if index_pos:
        index = os.path.basename(file_path)[index_pos[0]:index_pos[1] + 1]
    else:
        index = None
    with open(file_path, 'r') as of:
        if data_format == 'aqualog':
            # get header (the first line in this case the Ex wavelength)
            firstline = of.readline()

            # remove unwanted characters
            firstline = re.findall(r"\d+", firstline)
            header = np.array([list(map(int, firstline))])

            # get index (the first column, in this case the Em wavelength) and the EEM
            idx = []
            data = np.zeros(np.shape(header))
            line = of.readline()  # start reading from the second line
            while line:
                initial = (line.split())[0]
                # check if items only contains digits
                try:
                    initial = float(initial)
                    idx.append(initial)
                    # get fluorescence intensity data from each line
                    dataline = np.array([list(map(float, (line.split())[1:]))])
                    try:
                        data = np.concatenate([data, dataline])
                    except ValueError:
                        print('please check the consistancy of header and data dimensions:\n')
                        print('number of columns suggested by your header: ', np.size(data), '\n')
                        print('number of columns you have in your intensity data: ', np.size(dataline))
                        break
                except ValueError:
                    pass
                line = of.readline()
            of.close()
            idx = np.array(list(map(float, idx)))
            data = data[1:, :]

        # Transpose the data matrix to set Xaxis-Em and Yaxis-Ex due to the fact
        # that the wavelength range of Em is larger, and it is visually better to
        # set the longer axis horizontally.
        intensity = data.T
        em_range = idx
        ex_range = header[0]
        if em_range[0] > em_range[1]:
            em_range = np.flipud(em_range)
        if ex_range[0] > ex_range[1]:
            ex_range = np.flipud(ex_range)
        else:
            Warning(
                'The current version of eempy only supports reading files written in the "Aqualog (HORIBA) format."')
    return intensity, ex_range, em_range, index


def read_eem_dataset(folder_path: str, kw: str = 'PEM.dat', data_format: str = 'aqualog',
                     index_pos: Union[Tuple, List, None] = None,
                     custom_filename_list: Union[Tuple, List, None] = None, wavelength_alignment=False,
                     interpolation_method: str = 'linear'):
    """
    Import EEMs from a specific folder. Due to the differences between EEM files generated by different instruments, the
    type of data_format must be specified. The current version only supports importing Aqualog (HORIBA) files,
    which are named using the format "xxPEM.dat" by default. The blank file generate by aqualog ('xxBEM.dat') can
    also be read with this function.

    Parameters
    ----------
    folder_path: str
        The path to the folder containing EEMs.
    kw: str
        A keyword for searching EEM files whose filenames contain this keyword.
    data_format: str
        Specify the type of EEM data format.
    index_pos: str
        The starting and ending positions of index in filenames. For example, if you want to read the index "2024_01_01"
        from the file with the name "EEM_2024_01_01_PEM.dat", a tuple (4, 13) should be passed to this parameter.
    custom_filename_list: list or None
        If a list is passed, only the EEM files whose filenames are specified in the list will be imported.
    wavelength_alignment: bool
        Align the ex/em ranges of the EEMs. This is useful if the EEMs are measured with different ex/em ranges.
        Note that ex/em will be aligned according to the ex/em ranges with the smallest intervals among all the
        imported EEMs.
    interpolation_method: str
        The interpolation method used for aligning ex/em. It is only useful if wavelength_alignment=True.

    Returns
    -------
    eem_stack: np.ndarray (3d)
        A stack of imported EEM (intensities)
    ex_range: np.ndarray (1d)
        The excitation wavelengths
    em_range: np.ndarray (1d)
        The emission wavelengths
    indexes: list or None
        The list of EEM indexes (if index_pos is specified).
    """
    if not custom_filename_list:
        filename_list = get_filelist(folder_path, kw)
    else:
        filename_list = custom_filename_list
    path = folder_path + '/' + filename_list[0]
    intensity, ex_range, em_range, index = read_eem(path, data_format=data_format, index_pos=index_pos)
    num_datfile = len(filename_list)
    eem_stack = np.zeros([num_datfile, intensity.shape[0], intensity.shape[1]])
    eem_stack[0, :, :] = intensity
    indexes = [index]
    em_range_old = np.copy(em_range)
    ex_range_old = np.copy(ex_range)
    for n in range(1, len(filename_list)):
        path = folder_path + '/' + filename_list[n]
        intensity, ex_range, em_range, index = read_eem(path, data_format=data_format)
        indexes.append(index)
        if wavelength_alignment:
            em_interval_new = (np.max(em_range) - np.min(em_range)) / (em_range.shape[0] - 1)
            em_interval_old = (np.max(em_range_old) - np.min(em_range_old)) / (em_range_old.shape[0] - 1)
            ex_interval_new = (np.max(ex_range) - np.min(ex_range)) / (ex_range.shape[0] - 1)
            ex_interval_old = (np.max(ex_range_old) - np.min(ex_range_old)) / (ex_range_old.shape[0] - 1)
            if em_interval_new > em_interval_old:
                em_range_target = em_range_old
            else:
                em_range_target = em_range
            if ex_interval_new > ex_interval_old:
                ex_range_target = ex_range_old
            else:
                ex_range_target = ex_range
            if em_interval_new > em_interval_old or ex_interval_new > ex_interval_old:
                intensity = eem_interpolation(intensity, em_range, np.flip(ex_range), em_range_target,
                                              np.flip(ex_range_target), method=interpolation_method)
                em_range = np.copy(em_range_old)
                ex_range = np.copy(ex_range_old)
            if em_interval_new < em_interval_old or ex_interval_new < ex_interval_old:
                eem_stack = process_eem_stack(eem_stack, eem_interpolation, em_range_old, np.flip(ex_range_old),
                                              em_range_target,
                                              np.flip(ex_range_target))
        try:
            eem_stack[n, :, :] = intensity
        except ValueError:
            print('Check data dimension: ', filename_list[n])
        em_range_old = np.copy(em_range)
        ex_range_old = np.copy(ex_range)
    return eem_stack, ex_range, em_range, indexes


def read_abs(file_path, index_pos: Union[Tuple, List, None] = None, data_format='aqualog'):
    """
    Import UV absorbance data from aqualog UV absorbance file. This kind of file is named using the format
    "xxABS.dat" by the aqualog software by default.

    Parameters
    ----------------
    file_path: str
        The filepath to the UV absorbance file
    index_pos: None or tuple with two elements
        The starting and ending positions of index in filenames. For example, if you want to read the index "2024_01_01"
        from the file with the name "EEM_2024_01_01_PEM.dat", a tuple (4, 13) should be passed to this parameter.
    data_format: str
        Specify the type of UV absorbance data format

    Returns
    ----------------
    absorbance:np.ndarray (1d)
        The UV absorbance spectra
    ex_range: np.ndarray (1d)
        The excitation wavelengths
    index: str
        The index of the Absorbance spectrum.
    """
    if index_pos:
        index = os.path.basename(file_path)[index_pos[0]:index_pos[1] + 1]
    else:
        index = None
    with open(file_path, 'r') as of:
        if data_format == 'aqualog':
            line = of.readline()
            idx = []
            data = []
            while line:
                initial = float((line.split())[0])
                idx.append(initial)
                try:
                    value = float((line.split())[1])
                    data.append(value)
                except IndexError:
                    # if no absorbance at specific wavelength, set the value to nan
                    data.append(np.nan)
                line = of.readline()
            of.close()
            ex_range = np.flipud(idx)
            absorbance = np.flipud(data)
        else:
            Warning(
                'The current version of eempy only supports reading files written in the "Aqualog (HORIBA) format."')
    return absorbance, ex_range, index


def read_abs_dataset(folder_path, kw: str = 'PEM.dat', data_format: str = 'aqualog',
                     index_pos: Union[Tuple, List, None] = None, custom_filename_list: Union[Tuple, List, None] = None,
                     wavelength_alignment=False, interpolation_method: str = 'linear'):
    if not custom_filename_list:
        filename_list = get_filelist(folder_path, kw)
    else:
        filename_list = custom_filename_list
    path = folder_path + '/' + filename_list[0]
    absorbance, ex_range, index = read_abs(path, data_format=data_format, index_pos=index_pos)
    num_datfile = len(filename_list)
    abs_stack = np.zeros([num_datfile, absorbance.shape[0]])
    abs_stack[0, :] = absorbance
    indexes = [index]
    ex_range_old = ex_range
    for n in range(1, len(filename_list)):
        path = folder_path + '/' + filename_list[n]
        absorbance, ex_range, index = read_abs(path, data_format=data_format, index_pos=index_pos)
        indexes.append(index)
        if wavelength_alignment:
            ex_interval_new = (np.max(ex_range) - np.min(ex_range)) / (ex_range.shape[0] - 1)
            ex_interval_old = (np.max(ex_range_old) - np.min(ex_range_old)) / (ex_range_old.shape[0] - 1)
            if ex_interval_new > ex_interval_old:
                f = interp1d(ex_range, absorbance, kind=interpolation_method)
                absorbance = f(ex_range_old)
            if ex_interval_new < ex_interval_old:
                abs_stack_new = np.zeros([num_datfile, absorbance.shape[0]])
                for i in range(n):
                    f = interp1d(ex_range_old, abs_stack[i, :], kind=interpolation_method)
                    abs_stack_new[i, :] = f(ex_range)
                abs_stack = abs_stack_new
        abs_stack[n, :] = absorbance
        ex_range_old = ex_range
    return abs_stack, ex_range, filename_list, indexes


def read_reference_from_text(filepath):
    """
    Read reference data from text file. The reference data can be any 1D data (e.g., dissolved organic carbon
    concentration). This first line of the file should be a header, and then each following line contains one datapoint,
     without any separators other than line breaks.
    For example->
    '''
    DOC (mg/L)
    1.0
    2.5
    4.8
    '''

    Parameters
    ----------------
    filepath: str
        The filepath to the aqualog UV absorbance file

    Returns
    ----------------
    absorbance:np.ndarray (1d)
        The reference data
    header: str
        The header
    """
    reference_data = []
    with open(filepath, "r") as f:
        line = f.readline()
        header = line.split()[0]
        while line:
            try:
                line = f.readline()
                reference_data.append(float(line.split()[0]))
            except IndexError:
                pass
        f.close()
    return reference_data, header


def get_filelist(filedir, kw):
    """
    Get a list containing all filenames with a given keyword in a folder
    For example, this can be used for searching EEM files (with the keyword "PEM.dat")
    """
    filelist = os.listdir(filedir)
    datlist = [file for file in filelist if kw in file]
    return datlist


def read_parafac_model(filepath):
    """
    Import PARAFAC model from a text file written in the format suggested by OpenFluor (
    https://openfluor.lablicate.com/). Note that the models downloaded from OpenFluor normally don't have scores.

    Parameters
    ----------------
    filepath: str
        The filepath to the aqualog UV absorbance file

    Returns
    ----------------
    ex_df: pd.DataFrame
        Excitation loadings
    em_df: pd.DataFrame
        Emission loadings
    score_df: pd.DataFrame or None
        Scores (if there's any)
    info_dict: dict
        A dictionary containing the model information
    """
    with open(filepath, 'r') as f:
        line = f.readline().strip()
        line_count = 0
        while '#' in line:
            if "Fluorescence" in line:
                print("Reading fluorescence measurement info...")
            line = f.readline().strip()
            line_count += 1
        info_dict = {}
        while '#' not in line:
            phrase = line.split(sep='\t')
            if len(phrase) > 1:
                info_dict[phrase[0]] = phrase[1]
            else:
                info_dict[phrase[0]] = ''
            line = f.readline().strip()
            line_count += 1
        while '#' in line:
            if "Excitation" in line:
                print("Reading Ex/Em loadings...")
            line = f.readline().strip()
            line_count_spectra_start = line_count
            line_count += 1
        while "Ex" in line:
            line = f.readline().strip()
            line_count += 1
        line_count_ex = line_count
        ex_df = pd.read_csv(filepath, sep="\t", header=None, index_col=[0, 1],
                            skiprows=line_count_spectra_start + 1, nrows=line_count_ex - line_count_spectra_start - 1)
        component_label = ['component {rank}'.format(rank=r + 1) for r in range(ex_df.shape[1])]
        ex_df.columns = component_label
        ex_df.index.names = ['type', 'wavelength']
        while "Em" in line:
            line = f.readline().strip()
            line_count += 1
        line_count_em = line_count
        em_df = pd.read_csv(filepath, sep='\t', header=None, index_col=[0, 1],
                            skiprows=line_count_ex, nrows=line_count_em - line_count_ex)
        em_df.columns = component_label
        em_df.index.names = ['type', 'wavelength']
        score_df = None
        while '#' in line:
            if "Score" in line:
                print("Reading component scores...")
            line = f.readline().strip()
            line_count += 1
        line_count_score = line_count
        while 'Score' in line:
            line = f.readline().strip()
            line_count += 1
        while '#' in line:
            if 'end' in line:
                line_count_end = line_count
                score_df = pd.read_csv(filepath, sep="\t", header=None, index_col=[0, 1],
                                       skiprows=line_count_score, nrows=line_count_end - line_count_score)
                score_df.index = score_df.index.set_levels(
                    [score_df.index.levels[0], pd.to_datetime(score_df.index.levels[1])])
                score_df.columns = component_label
                score_df.index.names = ['type', 'time']
                print('Reading complete')
                line = f.readline().strip()
        f.close()
    return ex_df, em_df, score_df, info_dict


def read_parafac_models(datdir, kw):
    """
    Search all PARAFAC models in a folder by keyword in filenames and import all of them into a dictionary using
    read_parafac_model()
    """
    datlist = get_filelist(datdir, kw)
    parafac_results = []
    for f in datlist:
        filepath = datdir + '/' + f
        ex_df, em_df, score_df, info_dict = read_parafac_model(filepath)
        info_dict['filename'] = f
        d = {'info': info_dict, 'ex': ex_df, 'em': em_df, 'score': score_df}
        parafac_results.append(d)
    return parafac_results


# def get_timestamp_from_filename(filename, ts_format='%Y-%m-%d-%H-%M-%S', ts_start_position=0, ts_end_position=19):
#     ts_string = filename[ts_start_position:ts_end_position]
#     ts = datetime.strptime(ts_string, ts_format)
#     return ts


def str_to_datetime(ts_string, ts_format='%Y-%m-%d-%H-%M-%S'):
    return datetime.strptime(ts_string, ts_format)
