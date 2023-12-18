import os
import sys
import glob
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from enum import Enum
import subprocess
import platform

import webbrowser
import json
import csv

#
# CrownSegmentation
#

class CrownSegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Crown Segmentation - FiboSeg" 
    self.parent.categories = ["Segmentation"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["Mathieu Leclercq (University of North Carolina)", 
    "Juan Carlos Prieto (University of North Carolina)",
    "Martin Styner (University of North Carolina)",
    "Lucia Cevidanes (University of Michigan)",
    "Beatriz Paniagua (Kitware)",
    "Connor Bowley (Kitware)",
    "Antonio Ruellas (University of Michigan)",
    "Marcela Gurgel (University of Michigan)",
    "Marilia Yatabe (University of Michigan)",
    "Jonas Bianchi (University of Michigan)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This extension provides a GUI for a deep learning automated teeth segmentation algorithm. The inputs are 3D IOS scans, and 
the dental crowns are segmented according to the <a href="https://en.wikipedia.org/wiki/Universal_Numbering_System">Universal Number System</a>. <br>

<h2 style="color: #2e6c80;">Running the module :</h2>
 <br> <br>
- The input file must be a .vtk file or a MRMLModelNode of a IOS scan for a lower or upper jaw. The model works better with models of jaws with no wisdom teeth. 
You can find examples in the "Examples" folder. <br> <br> 

- Number of views: this sets the number of 2D views used for one prediction. A low number takes less time to compute, but results can be inaccurate.<br> <br>

- Model for segmentation: this is the path for the neural network model. Resolution: This sets the resolution of the 2D views. 320 px is recommended. 
Name of predicted labels: this is the name the array with the predicted labels on the output vtk file.   <br><br> 



<span style="color: ##2e6c80;"><strong>More options can be found in the "Advanced" section:</strong></span> <br><br> 


- Resolution: this sets the resolution of the 2D views used for the prediction. This should usually be set to 320px. <br><br>

- Name of predicted labels: The name of the VTK array that stores the labels for each vertex in the output surface file. <br><br>

- "Install/Check dependencies" button: This forces the installation of all dependencies. If you don't use this button the first time you run a prediction, it will 
automatically install all dependencies before starting the prediction. <br><br>

- "Create one output file for each label": Check this box if you want one separate output file for each tooth. <br><br>

- "Numbering system": lets you choose between <a href="https://en.wikipedia.org/wiki/Universal_Numbering_System">Universal Number System</a> and <a href="https://en.wikipedia.org/wiki/FDI_World_Dental_Federation_notation">FDI notation</a>.
<br><br>

When prediction is over, you can open the output surface as a MRML node in Slicer by pushing the "Open output surface".
You can change the color table in Slicer's "Models" module. <br><br>

More help can be found on the <a href="https://github.com/DCBIA-OrthoLab/SlicerDentalModelSeg">Github repository</a> for the extension.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""


#
# CrownSegmentationWidget
#

class InputChoice(Enum):
  VTK = 0
  MRML_NODE = 1
  FOLDER = 2

class CrownSegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation

    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False
    self.fileName = ""
    self.input = ""
    self.outputFolder = ""
    self.output  = ""
    self.lArrays = []
    self.model = "" 
    self.nbFiles = 1
    self.resolution = 256
    self.predictedId = ""
    self.rotation = None
    self.inputChoice = InputChoice.VTK
    self.lNodes = []
    self.MRMLNode = None
    self.log_path = os.path.join(slicer.util.tempDirectory(), 'process.log')
    self.time_log = 0 # for progress bar
    self.progress = 0
    self.currentPredDict = {}


  def setup(self):
    self.removeObservers()
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CrownSegmentation.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)


    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = CrownSegmentationLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # UI elements
    
    self.ui.dependenciesButton.connect('clicked(bool)',self.checkDependencies)

    # Inputs
    self.ui.applyChangesButton.connect('clicked(bool)',self.onApplyChangesButton)
    self.ui.rotationSpinBox.valueChanged.connect(self.onRotationSpinbox)
    self.ui.rotationSlider.valueChanged.connect(self.onRotationSlider)
    self.ui.browseSurfaceButton.connect('clicked(bool)',self.onBrowseSurfaceButton)
    self.ui.inputFolderPushButton.connect('clicked(bool)',self.onBrowseInputFolderButton)
    self.ui.browseModelButton.connect('clicked(bool)',self.onBrowseModelButton)
    self.ui.surfaceLineEdit.textChanged.connect(self.onEditSurfaceLine)
    self.ui.inputFolderLineEdit.textChanged.connect(self.onEditInputFolderLine)
    self.ui.modelLineEdit.textChanged.connect(self.onEditModelLine)    
    self.ui.githubButton.connect('clicked(bool)',self.onGithubButton)
    self.ui.checkBoxLatestModel.stateChanged.connect(self.useLatestModel)
    self.ui.checkBoxOverwrite.stateChanged.connect(self.overwrite)
    self.ui.surfaceComboBox.currentTextChanged.connect(self.onSurfaceModeChanged)
    self.ui.MRMLNodeComboBox.setMRMLScene(slicer.mrmlScene)
    self.ui.MRMLNodeComboBox.currentNodeChanged.connect(self.onNodeChanged)
    self.ui.MRMLNodeComboBox.setHidden(True)
    self.ui.inputFolderLineEdit.setHidden(True)
    self.ui.inputFolderPushButton.setHidden(True)

    # Advanced 
    self.ui.advancedCollapsibleButton.collapsed = 1 # Set to 1
    self.ui.predictedIdLineEdit.textChanged.connect(self.onEditPredictedIdLine)
    self.ui.resolutionComboBox.currentTextChanged.connect(self.onResolutionChanged)
    self.ui.installProgressBar.setEnabled(False)
    self.ui.installSuccessLabel.setHidden(True)
    self.ui.labelComboBox.currentTextChanged.connect(self.onFDI)

    # Outputs 
    self.ui.browseOutputButton.connect('clicked(bool)',self.onBrowseOutputButton)
    self.ui.outputLineEdit.textChanged.connect(self.onEditOutputLine)
    self.ui.outputFileLineEdit.textChanged.connect(self.onEditOutputLine)
    self.ui.openOutSurfButton.connect('clicked(bool)',self.onOpenOutSurfButton)
    self.ui.openOutFolderButton.connect('clicked(bool)',self.onOpenOutFolderButton)
    self.ui.resetButton.connect('clicked(bool)',self.onReset)
    self.ui.cancelButton.connect('clicked(bool)', self.onCancel)
    self.ui.progressLabel.setHidden(True)
    self.ui.openOutSurfButton.setHidden(True)
    self.ui.openOutFolderButton.setHidden(True)
    self.ui.cancelButton.setHidden(True)
    self.ui.doneLabel.setHidden(True)
    self.ui.githubButton.setHidden(True)
    

    #initialize variables
    if qt.QSettings().value('TeethSeg_ModelPath') != None:
      self.ui.modelLineEdit.setText(qt.QSettings().value('TeethSeg_ModelPath'))
    self.model = self.ui.modelLineEdit.text
    self.input = self.ui.surfaceLineEdit.text
    self.outputFolder = self.ui.outputLineEdit.text
    self.output = self.ui.outputLineEdit.text + self.ui.outputFileLineEdit.text
    self.predictedId = self.ui.predictedIdLineEdit.text
    self.resolution = int(self.ui.resolutionComboBox.currentText)
    self.rotation = self.ui.rotationSlider.value
    self.MRMLNode = slicer.mrmlScene.GetNodeByID(self.ui.MRMLNodeComboBox.currentNodeID)
    self.chooseFDI = self.ui.labelComboBox.currentIndex
    #print(self.MRMLNode.GetName())

    #Hidden
    self.ui.rotationSpinBox.setHidden(True)
    self.ui.label_3.setHidden(True)
    self.ui.rotationSlider.setHidden(True)
    self.ui.resolutionComboBox.setHidden(True)
    self.ui.label.setHidden(True)
    self.ui.dependenciesButton.setHidden(True)
    self.ui.installProgressBar.setHidden(True)



    # qt.QSettings().setValue("TeethSegVisited",None)
    if qt.QSettings().value('TeethSegVisited') is None:
        self.msg = qt.QMessageBox()
        self.msg.setText(f'Welcome to this module!\n'
          'The module works with Linux only. You also need a CUDA capable GPU.\n'
          'If you are running it for the first time, The installation of the dependencies will take time.\n' )
        self.msg.setWindowTitle("Welcome!")
        self.cb = qt.QCheckBox()
        self.cb.setText("Don't show this again")
        self.cb.stateChanged.connect(self.onCBchecked)
        self.msg.setCheckBox(self.cb)
        self.msg.exec_()


    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

    # Select default input nodes if nothing is selected yet to save a few clicks for the user
    if not self._parameterNode.GetNodeReference("InputVolume"):
      firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
      if firstVolumeNode:
        self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    # if inputParameterNode:
    #   self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True


    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch


    self._parameterNode.EndModify(wasModified)





  def onCBchecked(self):
    state = self.cb.checkState()
    if state==0:
      qt.QSettings().setValue("TeethSegVisited",None)
    else:
      qt.QSettings().setValue("TeethSegVisited",1)

      

  ###
  ### INPUTS
  ###

  def onBrowseSurfaceButton(self):
    newsurfaceFile = qt.QFileDialog.getOpenFileName(self.parent, "Select a surface", '', "VTK and STL files (*.vtk *.stl)")
    if newsurfaceFile != '':
      self.input = newsurfaceFile
      self.ui.surfaceLineEdit.setText(self.input)

    if self.ui.checkBoxOverwrite.checked :
      self.ui.outputLineEdit.setText(os.path.dirname(self.ui.surfaceLineEdit.text))
    #print(f'Surface directory : {self.surfaceFile}')


  def onBrowseInputFolderButton(self):
    newInputFolder = qt.QFileDialog.getExistingDirectory(self.parent, "Select a directory")
    if newInputFolder != '':
      self.input = newInputFolder
      print(self.input)
      self.ui.inputFolderLineEdit.setText(self.input)

    if self.ui.checkBoxOverwrite.checked :
      self.ui.outputLineEdit.setText(self.ui.inputFolderLineEdit.text)

    
    #print(f'Output directory : {self.output}')   


  def onBrowseModelButton(self):
    newModel = qt.QFileDialog.getOpenFileName(self.parent, "Select a model")
    if newModel != '':
      self.model = newModel
      self.ui.modelLineEdit.setText(self.model)
    #print(f'Surface directory : {self.surfaceFile}')

  def overwrite(self):
    if self.ui.checkBoxOverwrite.checked:
      self.ui.outputFileLineEdit.setEnabled(False)
      self.ui.outputLineEdit.setEnabled(False)
      self.ui.outputFileLineEdit.setText("None")
      print(self.ui.surfaceLineEdit.text)
      print(self.ui.surfaceComboBox.currentText)
      if self.ui.surfaceComboBox.currentText=="Select file":
        self.ui.outputLineEdit.setText(os.path.dirname(self.ui.surfaceLineEdit.text))
      else : 
        self.ui.outputLineEdit.setText(self.ui.inputFolderLineEdit.text)
        print(self.ui.inputFolderLineEdit.text)


    else : 
      self.ui.outputFileLineEdit.setEnabled(True)
      self.ui.outputLineEdit.setEnabled(True)
      self.ui.outputFileLineEdit.setText("predict")


  def useLatestModel(self):
    if self.ui.checkBoxLatestModel.checked:
      self.ui.browseModelButton.setEnabled(False)
      self.ui.modelLineEdit.setEnabled(False)
      self.ui.modelLineEdit.setText("latest")

    else : 
      self.ui.browseModelButton.setEnabled(True)
      self.ui.modelLineEdit.setEnabled(True)


  def onGithubButton(self):
    # webbrowser.open('https://github.com/MathieuLeclercq/fly-by-cnn/blob/master/src/py/FiboSeg/best_metric_model_segmentation2d_array_v2_5.pth')
    # webbrowser.open('https://github.com/MathieuLeclercq/fly-by-cnn/blob/master/src/py/challenge-teeth/checkpoints/07-21-22_val-loss0.169.pth')
    # webbrowser.open('https://github.com/DCBIA-OrthoLab/SlicerDentalModelSeg/releases/tag/v3.0')
    webbrowser.open('https://github.com/DCBIA-OrthoLab/Fly-by-CNN/releases/tag/3.0')


  def onEditModelLine(self):
    self.model = self.ui.modelLineEdit.text


  def onEditSurfaceLine(self):
    self.input = self.ui.surfaceLineEdit.text 


  def onEditInputFolderLine(self):
    self.input = self.ui.inputFolderLineEdit.text 

  def onRotationSlider(self):
    self.ui.rotationSpinBox.value = self.ui.rotationSlider.value
    self.rotation = self.ui.rotationSlider.value

  def onRotationSpinbox(self):
    self.ui.rotationSlider.value = self.ui.rotationSpinBox.value
    self.rotation = self.ui.rotationSlider.value

  def onSurfaceModeChanged(self):
    choice = self.ui.surfaceComboBox.currentText
    self.input = ""
    self.ui.MRMLNodeComboBox.setHidden(True)
    self.ui.surfaceLineEdit.setHidden(True)
    self.ui.browseSurfaceButton.setHidden(True)
    self.ui.inputFolderLineEdit.setHidden(True)
    self.ui.inputFolderPushButton.setHidden(True)
    self.ui.outputFileLineEdit.setHidden(False)
    self.ui.outputFileLabel.setHidden(False)



    if choice == 'Select file':
      self.inputChoice = InputChoice.VTK
      self.ui.surfaceLineEdit.setHidden(False)
      self.ui.browseSurfaceButton.setHidden(False)
      self.input = self.ui.surfaceLineEdit.text
      self.ui.inputFolderLineEdit.setText("")
    elif choice == 'Select MRMLModelNode':
      self.inputChoice = InputChoice.MRML_NODE
      self.ui.MRMLNodeComboBox.setHidden(False)
    else: # Select folder 
      self.inputChoice = InputChoice.FOLDER
      self.ui.inputFolderLineEdit.setHidden(False)
      self.ui.inputFolderPushButton.setHidden(False)
      self.input = self.ui.inputFolderLineEdit.text
      # self.ui.outputFileLineEdit.setText("")
      # self.ui.surfaceLineEdit.setText("")
      # self.ui.outputFileLabel.setHidden(True)
      # self.ui.outputFileLineEdit.setHidden(True)




  def onNodeChanged(self):
    self.MRMLNode = slicer.mrmlScene.GetNodeByID(self.ui.MRMLNodeComboBox.currentNodeID)
    if self.MRMLNode is not None:
      print(self.MRMLNode.GetName())


  def writeVTKFromNode(self):
    poly = self.MRMLNode.GetPolyData()    
    filename = self.output[0:-4]+"_input.vtk"
    print(filename)
    polydatawriter = vtk.vtkPolyDataWriter()
    polydatawriter.SetFileName(filename)
    polydatawriter.SetInputData(poly)
    polydatawriter.Write()
    return filename

  ###
  ### ADVANCED
  ###


  def onEditPredictedIdLine(self):
    self.predictedId = self.ui.predictedIdLineEdit.text


  def onResolutionChanged(self):
    self.resolution = int(self.ui.resolutionComboBox.currentText)

  def checkDependencies(self): #TODO: ALSO CHECK FOR CUDA 
    self.ui.dependenciesButton.setEnabled(False)
    self.ui.applyChangesButton.setEnabled(False)
    self.ui.installProgressBar.setEnabled(True)
    self.installLogic = CrownSegmentationLogic('-1',0,0,0,0,0,0,0,0) # -1: flag so that CLI module knows it's only to install dependencies
    self.installLogic.process()
    self.ui.installProgressBar.setRange(0,0)
    self.installObserver = self.installLogic.cliNode.AddObserver('ModifiedEvent',self.onInstallationProgress)
    

  def onInstallationProgress(self,caller,event):
    if self.installLogic.cliNode.GetStatus() & self.installLogic.cliNode.Completed:
      if self.installLogic.cliNode.GetStatus() & self.installLogic.cliNode.ErrorsMask:
        # error
        errorText = self.installLogic.cliNode.GetErrorText()
        print("CLI execution failed: \n \n" + errorText)
        msg = qt.QMessageBox()
        msg.setText(f'There was an error during the installation:\n \n {errorText} ')
        msg.setWindowTitle("Error")
        msg.exec_()
      else:
        # success
        print('SUCCESS')
        print(self.installLogic.cliNode.GetOutputText())
        self.ui.installSuccessLabel.setHidden(False)
      self.ui.installProgressBar.setRange(0,100)
      self.ui.installProgressBar.setEnabled(False)
      self.ui.dependenciesButton.setEnabled(True)
      self.ui.applyChangesButton.setEnabled(True)


  def onFDI(self):
    self.chooseFDI = self.ui.labelComboBox.currentIndex
    print(f'chooseFDI: {self.chooseFDI}')



  ###
  ### OUTPUTS
  ###

  def onOpenOutSurfButton(self):
    print(self.currentPredDict["output"])
    jaw_model = slicer.util.loadModel(self.currentPredDict["output"])
    jaw_model.GetDisplayNode().SetActiveScalar(self.currentPredDict["PredictedID"], vtk.vtkAssignAttribute.POINT_DATA)
    jaw_model.GetDisplayNode().SetAndObserveColorNodeID("vtkMRMLColorTableNodeFileViridis.txt")
    jaw_model.GetDisplayNode().SetScalarVisibility(True)

  def onOpenOutFolderButton(self):
    webbrowser.open(self.output)

  def onBrowseOutputButton(self):
    newoutputFolder = qt.QFileDialog.getExistingDirectory(self.parent, "Select a directory")
    if newoutputFolder != '':
      if newoutputFolder[-1] != "/":
        newoutputFolder += '/'
      self.outputFolder = newoutputFolder
      print(self.outputFolder)
      self.ui.outputLineEdit.setText(self.outputFolder)
      print(self.output)
    #print(f'Output directory : {self.output}')   


  def onEditOutputLine(self): # called when either output folder line or output file line is modified
    self.outputFolder = self.ui.outputLineEdit.text
    self.output = self.ui.outputLineEdit.text + self.ui.outputFileLineEdit.text
  ###
  ### PROCESS
  ###



  def onApplyChangesButton(self):

    #if ((self.inputChoice is InputChoice.MRML_NODE and self.MRMLNode is not None) or os.path.isfile(self.input) or os.path.isdir(self.input))  and os.path.isdir(self.outputFolder) and os.path.isfile(self.model):
    if not(os.path.isdir(self.outputFolder) and (os.path.isfile(self.model) or self.model=="latest")):
      print('Error.')
      msg = qt.QMessageBox()
      if not(os.path.isdir(self.outputFolder)):
        msg.setText("Output directory : \nIncorrect path.")
        print('Error: Incorrect path for output directory.')
        self.ui.outputLineEdit.setText('')
        print(f'output folder : {self.outputFolder}')

      elif (not(os.path.isfile(self.model)) and self.model!="latest"):
        msg.setText("Model : \nIncorrect path.")
        print('Error: Incorrect path for model.')
        self.ui.modelLineEdit.setText('')
        print(f'model path: {self.model}')

      else:
        msg.setText('Unknown error.')

      msg.setWindowTitle("Error")
      msg.exec_()
      return

    elif not((self.inputChoice is InputChoice.MRML_NODE and self.MRMLNode is not None) or os.path.isfile(self.input) or os.path.isdir(self.input)):
      print('Error.')
      msg = qt.QMessageBox()
      if self.inputChoice is InputChoice.VTK and not(os.path.isfile(self.surfaceFile)):        
        msg.setText("Surface directory : \nIncorrect path.")
        print('Error: Incorrect path for surface directory.')
        self.ui.surfaceLineEdit.setText('')
        print(f'surface folder : {self.surfaceFile}')

      elif self.inputChoice is InputChoice.MRML_NODE and self.MRMLNode is None:        
        msg.setText("Input surface : \nPlease select a MRML node.")
        print('Error: No MRML node was selected.')
        self.ui.surfaceLineEdit.setText('')
        print(f'MRML node : {self.MRMLNode}')

      else:
        msg.setText('Unknown error.')

      msg.setWindowTitle("Error")
      msg.exec_()
      return

    else:
      # Ready to start cli module
      ready = True 
      system = platform.system()
      if system == "Windows" :
          wsl = self.is_ubuntu_installed()
          if wsl :
            ready = True
          else :
            messageBox = qt.QMessageBox()
            text = "Code can't be launch. \nWSL is not installed, please download the installer and follow the instructin here : https://github.com/DCBIA-OrthoLab/SlicerAutomatedDentalTools/releases/download/wsl2_windows/installer_wsl2.zip\nDownloading may be blocked by Chrome, this is normal, just authorize it."
            ready = False
            messageBox.information(None, "Information", text)
              
      if ready :
        self.ui.applyChangesButton.setEnabled(False)
        self.ui.progressBar.setEnabled(True)
        if self.inputChoice is InputChoice.MRML_NODE: # MRML node
          filename = self.writeVTKFromNode()
          self.logic = CrownSegmentationLogic(filename,
                                              "None",
                                              "None",
                                              self.ui.outputLineEdit.text,
                                              self.model, 
                                              self.predictedId,
                                              self.ui.sepOutputsCheckbox.isChecked(),
                                              self.chooseFDI,
                                              self.log_path,
                                              self.ui.checkBoxOverwrite.checked,
                                              self.ui.outputFileLineEdit.text,
                                              "None")

        else: # input folder/file
          input_vtk = "None"
          input_stl = "None"
          input_csv = "None"
          vtk_folder = "None"
          if os.path.isfile(self.input):
              extension = os.path.splitext(self.input)[1]
              if extension == ".vtk":
                input_vtk = self.input
              elif extension == ".stl" :
                input_stl = self.input
                
          elif os.path.isdir(self.input):
            input_csv = self.create_csv()
            vtk_folder = self.input

          

          
          self.logic = CrownSegmentationLogic(input_vtk,
                                              input_stl,
                                              input_csv,
                                              self.ui.outputLineEdit.text,
                                              self.model, 
                                              self.predictedId, 
                                              self.ui.sepOutputsCheckbox.isChecked(),
                                              self.chooseFDI,
                                              self.log_path,
                                              self.ui.checkBoxOverwrite.checked,
                                              self.ui.outputFileLineEdit.text,
                                              vtk_folder)
        #TEST
        # model = self.model
        # if model == "latest":
        #     model = None
        # command_to_execute = ['conda','run','-n','shapeAxi',f'dentalmodelseg --vtk {input_vtk} --stl {input_stl} --csv {input_csv} --out {self.ui.outputLineEdit.text} --overwrite {self.ui.checkBoxOverwrite.checked} --model {model} --crown_segmentation {self.ui.sepOutputsCheckbox.isChecked()} --array_name {self.predictedId} --fdi {self.chooseFDI} --suffix {self.ui.outputFileLineEdit.text} --vtk_folder {vtk_folder}']
        # command_to_execute = [
        #     'conda', 'run', '-n', 'shapeAxi', 
        #     'dentalmodelseg', 
        #     '--vtk', '/home/luciacev/Documents/Gaelle/Data/CrownSegmentation/vtk_no_segmented/T1_nosegmented.vtk', 
        #     '--stl', 'None', 
        #     '--csv', 'None', 
        #     '--out', '/home/luciacev/Documents/Gaelle/Data/CrownSegmentation/output/', 
        #     '--overwrite', 'False', 
        #     '--model', 'None', 
        #     '--crown_segmentation', 'False', 
        #     '--array_name', 'Universal_ID', 
        #     '--fdi', '0', 
        #     '--suffix', 'predict', 
        #     '--vtk_folder', 'None'
        # ]

        # command_to_execute = ['/home/luciacev/miniconda3/bin/conda','run','-n','shapeAxi','python','/home/luciacev/Desktop/SlicerDentalModelSeg/CrownSegmentation/test.py']
        # command_to_execute = ['conda','run','-n','shapeAxi','python','/home/luciacev/Desktop/SlicerDentalModelSeg/CrownSegmentation/test.py']
        


        # path_env = os.environ.get('PATH', '')

        # # Afficher la variable PATH
        # print("PATH complet:")
        # print(path_env)

        # # Séparer la variable PATH en différents chemins
        # path_list = path_env.split(os.pathsep)

        # # Filtrer pour trouver les chemins qui contiennent 'miniconda3' ou 'anaconda3'
        # conda_paths = [path for path in path_list if 'miniconda3' in path or 'anaconda3' in path]


        # print("on run")
        # result = subprocess.run(command_to_execute, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,env=slicer.util.startupEnvironment())

        # if result.returncode != 0:
        #     print(f"Error creating the environment. Return code: {result.returncode}")
        #     print("result.stdout : ","*"*150)
        #     print(result.stdout)
        #     print("result.stderr : ","*"*150)
        #     print(result.stderr)
        # else:
        #     print(result.stdout)
        #     print("Environment created successfully.")


        #END TEST
        self.logic.process()
        #self.processObserver = self.logic.cliNode.AddObserver('ModifiedEvent',self.onProcessUpdate)
        self.addObserver(self.logic.cliNode,vtk.vtkCommand.ModifiedEvent,self.onProcessUpdate)
        self.onProcessStarted()


  def create_csv(self):
    file_path = os.path.abspath(__file__)
    folder_path = os.path.dirname(file_path)
    csv_file = os.path.join(folder_path,"list_file.csv")
    with open(csv_file, 'w', newline='') as fichier:
        writer = csv.writer(fichier)
        # Écrire l'en-tête du CSV
        writer.writerow(["surf"])

        # Parcourir le dossier et ses sous-dossiers
        for root, dirs, files in os.walk(self.input):
            for file in files:
                if file.endswith(".vtk") or file.endswith(".stl"):
                    # Écrire le chemin complet du fichier dans le CSV
                    writer.writerow([os.path.join(root, file)])

    return csv_file


  def is_ubuntu_installed(self)->bool:
      '''
      Check if wsl is install with Ubuntu
      '''
      result = subprocess.run(['wsl', '--list'], capture_output=True, text=True)
      output = result.stdout.encode('utf-16-le').decode('utf-8')
      clean_output = output.replace('\x00', '')  # Enlève tous les octets null

      return 'Ubuntu' in clean_output

  def onProcessStarted(self):    
    self.currentPredDict["rotation"] = self.rotation
    self.currentPredDict["PredictedID"] = self.predictedId
    self.currentPredDict["output"] = self.output
    self.ui.doneLabel.setHidden(True)
    self.ui.openOutSurfButton.setHidden(True)
    self.ui.cancelButton.setHidden(False)
    self.ui.cancelButton.setEnabled(True)
    self.ui.resetButton.setEnabled(False)
    if os.path.isdir(self.input):
      self.nbFiles = len(glob.glob(f"{self.input}/*.vtk"))
    else:
      self.nbFiles = 1
    self.ui.progressBar.setValue(0)
    self.progress = 0
    self.ui.progressBar.setEnabled(True)
    self.ui.progressBar.setHidden(False)
    self.ui.progressBar.setTextVisible(True)
    self.ui.progressLabel.setHidden(False)

    qt.QSettings().setValue("TeethSeg_ModelPath",self.model)
    qt.QSettings().setValue("TeethSegVisited",1)



  def onProcessUpdate(self,caller,event):
    # check log file
    if os.path.isfile(self.log_path):
      time = os.path.getmtime(self.log_path)
      if time != self.time_log:
        # if progress was made
        self.time_log = time
        self.progress += 1
        progressbar_value = (self.progress -1) /self.nbFiles * 100
        #print(f'progressbar value {progressbar_value}')
        if progressbar_value < 100 :
          self.ui.progressBar.setValue(progressbar_value)
        else:
          self.ui.progressBar.setValue(99)

    if self.logic.cliNode.GetStatus() & self.logic.cliNode.Completed:
      # process complete
      self.ui.applyChangesButton.setEnabled(True)
      self.ui.resetButton.setEnabled(True)
      self.ui.progressLabel.setHidden(False)         
      self.ui.cancelButton.setEnabled(False)
      self.ui.progressBar.setEnabled(False)
      self.ui.progressBar.setHidden(True)
      self.ui.progressLabel.setHidden(True)

      if self.logic.cliNode.GetStatus() & self.logic.cliNode.ErrorsMask:
        # error
        errorText = self.logic.cliNode.GetErrorText()
        print("CLI execution failed: \n \n" + errorText)
        msg = qt.QMessageBox()
        msg.setText(f'There was an error during the process:\n \n {errorText} ')
        msg.setWindowTitle("Error")
        msg.exec_()

      else:
        # success
        print('PROCESS DONE.')
        file_path = os.path.abspath(__file__)
        folder_path = os.path.dirname(file_path)
        csv_file = os.path.join(folder_path,"list_file.csv")
        if os.path.exists(csv_file):
          os.remove(csv_file)
        print(self.logic.cliNode.GetOutputText())
        self.ui.doneLabel.setHidden(False)
        if os.path.isdir(self.output):
          self.ui.openOutFolderButton.setHidden(False)
        elif os.path.isfile(self.output):
          self.ui.openOutSurfButton.setHidden(False) 
        
  def onReset(self):
    self.ui.outputLineEdit.setText("")
    self.ui.surfaceLineEdit.setText("")
    self.ui.rotationSpinBox.value = 45
    self.ui.applyChangesButton.setEnabled(True)
    self.ui.progressLabel.setHidden(True)
    self.ui.openOutSurfButton.setHidden(True)
    self.ui.openOutFolderButton.setHidden(True)
    self.ui.progressBar.setValue(0)
    self.ui.doneLabel.setHidden(True)
    self.ui.surfaceComboBox.setCurrentIndex(0)
    self.ui.labelComboBox.setCurrentIndex(0)
    self.ui.sepOutputsCheckbox.setChecked(False)
    self.removeObservers()    

  def onCancel(self):
    self.logic.cliNode.Cancel()
    self.ui.applyChangesButton.setEnabled(True)
    self.ui.resetButton.setEnabled(True)
    self.ui.progressBar.setEnabled(False)
    self.ui.progressBar.setRange(0,100)
    self.ui.progressLabel.setHidden(True)
    self.ui.cancelButton.setEnabled(False)
    self.removeObservers()    
    print("Process successfully cancelled.")


#
# CrownSegmentationLogic
#

class CrownSegmentationLogic(ScriptedLoadableModuleLogic):
  """
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, input_vtk = None,input_stl = None, input_csv = None,output=None,model=None,predictedId=None,sepOutputs=None,chooseFDI=None,logPath=None,overwrite=False,suffix="None",vtk_folder="None"):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.input_vtk = input_vtk
    self.input_stl = input_stl
    self.input_csv = input_csv
    self.output = output
    self.model = model
    self.predictedId = predictedId
    self.sepOutputs = sepOutputs
    self.chooseFDI = chooseFDI
    self.logPath = logPath
    self.nbOperation = 0
    self.progress = 0
    self.cliNode = None
    self.installCliNode = None
    self.overwrite = overwrite
    self.suffix = suffix
    self.vtk_folder = vtk_folder
    """
    print(f"model: {self.model}")
    print(f'input : {self.input}')
    print(f'outptutfile : {self.output}')
    print(f'resolution : {self.resolution}')
    print(f'rotation : {self.rotation}')
    print(f'predictedId : {self.predictedId}')
    """



  def process(self):
    parameters = {}
    parameters ["input_vtk"] =self.input_vtk
    parameters ["input_stl"] =self.input_stl
    parameters ["input_csv"] =self.input_csv
    parameters ["output"] = self.output
    parameters ['model'] = self.model
    parameters ['predictedId'] = self.predictedId
    parameters ['sepOutputs'] = str(self.sepOutputs)
    parameters ['chooseFDI'] = int(self.chooseFDI)
    parameters ['logPath'] = self.logPath
    parameters ['overwrite'] = str(self.overwrite)
    parameters ['name_env'] = "shapeAxi"
    parameters ['suffix'] = self.suffix
    parameters ['vtk_folder'] = self.vtk_folder
    print ('parameters : ', parameters)
    flybyProcess = slicer.modules.crownsegmentationcli
    self.cliNode = slicer.cli.run(flybyProcess,None, parameters)    
    return flybyProcess

