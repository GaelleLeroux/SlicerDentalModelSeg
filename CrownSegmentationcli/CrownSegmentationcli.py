#!/usr/bin/env python-real



import sys
import os
import argparse
import platform


# from CondaSetUp import  CondaSetUpCall,CondaSetUpCallWsl



  

def main(args):
    print('start crown segmentation cli')
    model = args.model
    if args.model == "latest":
      model = None
    else :
      if platform.system()=="Linux":
        model=model
      else :
        model = windows_to_linux_path(model)
    
    if platform.system()=="Linux":
      print("bonjour")
          
    elif platform.system()=="Windows":
      print("*"*150)
      command = [f'dentalmodelseg --vtk \"{windows_to_linux_path(args.input_vtk)}\" --stl \"{windows_to_linux_path(args.input_stl)}\" --csv \"{windows_to_linux_path(args.input_csv)}\" --out \"{windows_to_linux_path(args.out)}\" --overwrite \"{args.overwrite}\" --model \"{model}\" --crown_segmentation \"{args.crown_segmentation}\" --array_name \"{args.array_name}\" --fdi \"{args.fdi}\" --suffix \"{args.suffix}\" --vtk_folder \"{windows_to_linux_path(args.vtk_folder)}\"']
      print("An exemple of use cand be find into the code of the module crownsegmentation")
      print("You need to check if wsl is installed and if the path to miniconda is setup in SlicerConda extension")
      print("In your module create an object CondaSetUpCallWsl from CondaSetUp ex: conda_wsl = CondaSetUpCallWsl() ")
      print(f"the command you need to create is : f{command} ")
      print("Run the segmentation of the crown with : conda_wsl.condaRunCommand(command, 'shapeaxi') ")
      



def windows_to_linux_path(windows_path):
      '''
      Convert a windows path to a wsl path
      '''
      windows_path = windows_path.strip()

      path = windows_path.replace('\\', '/')

      if ':' in path:
          drive, path_without_drive = path.split(':', 1)
          path = "/mnt/" + drive.lower() + path_without_drive

      return path




if __name__ == '__main__':
    print("Starting crownsegmentation cli")
    parser = argparse.ArgumentParser()
    parser.add_argument('input_vtk',type=str)
    parser.add_argument('input_stl',type=str)
    parser.add_argument('input_csv',type = str)
    parser.add_argument('out',type=str)
    parser.add_argument('overwrite',type=str)
    parser.add_argument('model',type=str)
    parser.add_argument('crown_segmentation',type=str)
    parser.add_argument('array_name',type=str)
    parser.add_argument('fdi',type=str)
    parser.add_argument('suffix',type=str)
    parser.add_argument('vtk_folder',type=str)
    args = parser.parse_args()
    print("args : ",args)
    main(args)

