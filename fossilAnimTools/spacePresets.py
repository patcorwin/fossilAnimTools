'''
Tool to switch groups of controls to specific spaces.

..  todo::
    * Disable viewport when running to speed it up
    * Option to autorun Euler filter

    * When a new file is opened, just clear everything (which it should be doing
        but maybe the scriptJob is messed up).
    * Better indication that something is wrong the control exists but the space doesn't
    * Eventually this will need to support multiple characters.
    
    Low priority
    * If the file is deleted during that session, it doesn't clear from local/public list
'''

from __future__ import absolute_import, division, print_function

import collections
import copy
from functools import partial
import itertools
import json
import logging
import os
import re

from PySide2 import QtWidgets
from shiboken2 import wrapInstance
from maya import OpenMayaUI

from pymel.core import columnLayout, currentTime, cutKey, deleteUI, \
    getAttr, keyframe, playbackOptions, promptDialog, PyNode, \
    select, selected, setKeyframe, scriptJob, window

from pdil.add import shortName, simpleName

from pdil import core, lib
from pdil.tool import fossil

from .spacepresetgui import Ui_Form
from .spacePrestsPrompt_qtui import Ui_Dialog

log = logging.getLogger(__name__)
presetLog = logging.getLogger('presetSwitching')
presetLog.setLevel( logging.DEBUG )


try:
    basestring # noqa
except Exception:
    basestring = str


if '_previouslyLoaded' not in globals():
    _previouslyLoaded = None


ACTIVATE_KEY = '# Activate'


class SpacePresets(QtWidgets.QWidget):

    name = 'SpacePresets'
    
    presetLocations = { 'local': os.environ['maya_app_dir'] + '/SpacePresets' }
    
    @classmethod
    @core.alt.name( 'Space Presets' )
    def run(cls):
        if window(cls.name, ex=True):
            deleteUI(cls.name)
    
    
    @property
    def presetFilepath(self):
        return self.presetFiles[ self.ui.presetChooser.currentText() ]
            
    
    @classmethod
    def asMelGui(cls):
        
        melLayout = columnLayout(adj=True)
        ptr = OpenMayaUI.MQtUtil.findLayout( melLayout.name() )
        widget = wrapInstance( long(ptr), QtWidgets.QWidget)  # noqa Despite findLayout, must cast to widget and use .layout()
        
        ui = cls()
        widget.layout().addWidget(ui)
        
        return melLayout, ui
    
    def __init__(self, parent=None):
        super(SpacePresets, self).__init__()
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        
        # Sets the control select button portion to stretch
        header = self.ui.profileTable.horizontalHeader()
        header.setSectionResizeMode(0, header.Stretch)
        
        self.mainControllers = []
        self.presetFiles = {}
        self.profiles = {}
        
        self.curProfile = {}
        
        self.populateCharacterChooser()
        self.populatePresetChooser()

        self.ui.presetChooser.currentTextChanged.connect(self.setPreset)
        self.ui.newPreset.clicked.connect( self.addNewPreset )
        
        self.ui.profileChooser.currentTextChanged.connect(self.setProfile)
        self.ui.newProfile.clicked.connect( self.profileNew )
        self.ui.rename.clicked.connect( self.profileRename )
        self.ui.clone.clicked.connect( self.profileClone )
        self.ui.deleteProfile.clicked.connect( self.profileDelete )
        
        self.ui.applyFrame.clicked.connect( partial(self.applySwitch, 'frame') )
        self.ui.applyRange.clicked.connect( partial(self.applySwitch, 'range') )
        self.ui.applySelected.clicked.connect( partial(self.applySwitch, 'selected') )
        self.ui.applyAll.clicked.connect( partial(self.applySwitch, 'all') )
        
        self.ui.addControls.clicked.connect( self.addSelectedControl )
        
        self.profileModifiers = [self.ui.newProfile, self.ui.rename, self.ui.clone, self.ui.deleteProfile]
        self.applyButtons = [self.ui.applyFrame, self.ui.applyRange, self.ui.applySelected, self.ui.applyAll]
    
        self.enableProfileGui(False)
    
    
    def applySwitch(self, mode):
        apply(self.curProfile, mode)
    
    
    def enableProfileGui(self, val):
    
        for button in itertools.chain(self.profileModifiers, self.applyButtons):
            button.setEnabled(val)
        
        self.ui.addControls.setEnabled(val)
        

    def populateCharacterChooser(self):
        self.mainControllers = core.findNode.mainControls()
        self.ui.characterChooser.clear()
        self.ui.characterChooser.addItems( ['-'] + [main.name() for main in self.mainControllers] )
    
    
    def populatePresetChooser(self):
        '''
        Fills are options for the preset files.
        '''
        
        self.presetFiles = collections.OrderedDict({'-': ''}) # { <label>: <file path> }
        self.ui.presetChooser.clear()
        
        for folder in self.presetLocations.values():
            if not os.path.exists(folder):
                os.makedirs(folder)
            
            for filename in os.listdir(folder):
                if filename.lower().endswith('.json'):
                    name = filename[:-5]
                    
                    if name in self.presetFiles:
                        name = os.path.basename(folder) + '/' + name
                        i = 0
                        while name in self.presetFiles:
                            name += str(i)
                    
                    self.presetFiles[name] = folder + '/' + filename
        
        self.ui.presetChooser.addItems( list(self.presetFiles.keys()) )


    def setPreset(self, presetName):
        '''
        Callback when a preset is chosen, updates the profileChooser.
        '''
        
        self.profiles = {}
        
        if presetName and presetName != '-':
            filename = self.presetFiles[presetName]
        
            with open(filename, 'r') as fid:
                self.profiles = json.load(fid, object_pairs_hook=collections.OrderedDict)
            
            self.populateProfileChooser()
        else:
            self.clearProfileChooser()
            
        self.ui.newProfile.setEnabled(True)
    
    
    def populateProfileChooser(self):
        self.clearProfileChooser()
        self.ui.profileChooser.addItems( list(self.profiles) )
    
    
    def clearProfileChooser(self):
        self.ui.profileChooser.clear()
        self.curProfile = {}
    
    
    def setProfile(self, profileName):
        log.debug('set profile ' + profileName)
        self.clearControlSpaces()

        if not profileName:
            return

        self.curProfile = collections.OrderedDict()
        
        # Get controls from the character chooser, defaulting to all
        index = self.ui.characterChooser.currentIndex() - 1 # First item is blank so offset by 1
        if index >= 0:
            allControls = core.findNode.controllers(main=self.mainControllers[index])
        else:
            allControls = core.findNode.controllers()
    
        nameMap = {shortName(ctrl): ctrl for ctrl in allControls}
        
        items = self.profiles[ profileName ].items()
        self.ui.profileTable.setRowCount( len(items) )
        
        for i, (ctrlName, space) in enumerate(items):
                        
            if ctrlName in nameMap:
                self.curProfile[nameMap[ctrlName]] = space
                self.addRow( i, nameMap[ctrlName], space )
                
            elif isinstance(ctrlName, PyNode):
                self.curProfile[ctrlName] = space
                self.addRow( i, ctrlName, space )
                
            else:
                self.curProfile[ctrlName] = space
                self.addEmpty( i, ctrlName, space )
        
        self.profiles[ profileName ] = self.curProfile
        
        self.enableProfileGui(True)
    
    
    def clearControlSpaces(self):
        self.ui.profileTable.clearContents()
        self.ui.profileTable.setRowCount(0)


    def addNewPreset(self):
        
        dialog = AddPresetDialog( list(self.presetLocations.keys()) )
        dialog.exec_()
        
        if dialog.result() != dialog.DialogCode.Accepted:
            return
            
        name = dialog.ui.nameEntry.text()
        location = dialog.ui.location.currentText()
        
        folder = self.presetLocations[location]
        with open( folder + '/' + name + '.json', 'w' ) as fid:
            fid.write('{}')
        
        self.populatePresetChooser()


    def addRow(self, row, ctrl, space):
        name = simpleName(ctrl)
        selectButton = QtWidgets.QPushButton( name )
        selectButton.clicked.connect( partial(select, ctrl) )
        
        spaceChooser = QtWidgets.QComboBox()
        spaceChooser.addItems( fossil.space.getNames(ctrl) + [ACTIVATE_KEY] )
        spaceChooser.setCurrentText(space)
        spaceChooser.currentTextChanged.connect( partial(self.setSpace, ctrl) )
        
        removeButton = QtWidgets.QPushButton('X')
        removeButton.clicked.connect( partial(self.removeControl, ctrl ) )
        
        #self.ui.profileTable.setItem(row, 0, QtWidgets.QTableWidgetItem(ctrl.name) )
        self.ui.profileTable.setCellWidget(row, 0, selectButton )
        self.ui.profileTable.setCellWidget(row, 1, spaceChooser )
        self.ui.profileTable.setCellWidget(row, 2, removeButton )

    
    def addEmpty(self, row, name, space):
        self.ui.profileTable.setItem(row, 0, QtWidgets.QTableWidgetItem('MISSING ' + name) )
        self.ui.profileTable.setItem(row, 1, QtWidgets.QTableWidgetItem(space) )
        
        removeButton = QtWidgets.QPushButton('X')
        removeButton.clicked.connect( partial(self.removeControl, name ) )
        
        self.ui.profileTable.setCellWidget(row, 2, removeButton )

    
    def removeControl(self, controlName):
        log.debug( 'Removing {} type:{}'.format(controlName, type(controlName)) )
        del self.curProfile[controlName]
        self.autoSave()
        self.setProfile( self.ui.profileChooser.currentText() )
    

    def profileNameValidator(self, name):
        if name in self.profiles:
            return 'A profile of that name already exists, choose another'


    def profileRefresh(self, name):
        self.autoSave()
        self.populateProfileChooser()
        if name:
            self.setProfile(name)


    def profileNew(self):
        
        name = profileNamePrompt(validator=self.profileNameValidator)
        if not name:
            return
        
        self.profiles[name] = {}
        
        self.profileRefresh(name)
    
    
    def profileRename(self):
        currentProfileName = self.ui.profileChooser.currentText()
        
        name = profileNamePrompt(validator=self.profileNameValidator)
        if not name:
            return
        
        self.profiles[name] = self.profiles[currentProfileName]
        del self.profiles[currentProfileName]
        
        self.profileRefresh(name)


    def profileClone(self):
        currentProfileName = self.ui.profileChooser.currentText()
        
        name = profileNamePrompt(validator=self.profileNameValidator)
        if not name:
            return
        
        self.profiles[name] = copy.deepcopy(self.profiles[currentProfileName])
        
        self.profileRefresh(name)


    def profileDelete(self):
        currentProfileName = self.ui.profileChooser.currentText()
        
        del self.profiles[currentProfileName]
        
        self.profileRefresh(None)


    def setSpace(self, ctrl, space):
        self.curProfile[ctrl] = space
        self.autoSave()


    def addSelectedControl(self):
        
        newRows = []
        
        # Verify we have a control, with spaces, not already in the preset
        for obj in selected():
            names = fossil.space.getNames(obj)
            log.debug( 'Grabbing -- Obj: {}, spaces: {}'.format(obj, names) )
            
            motionOnly = False
            if not names:
                if not fossil.controllerShape.getSwitcherPlug(obj):
                    continue
                else:
                    motionOnly = True

            if obj in self.curProfile:
                continue

            # Finally add it to the preset, or '#' if it's a motion only switch
            if motionOnly:
                self.curProfile[obj] = ACTIVATE_KEY
            else:
                self.curProfile[obj] = fossil.space.get(obj)

            newRows.append( (obj, self.curProfile[obj]) )
        
        prevCount = self.ui.profileTable.rowCount()
        self.ui.profileTable.setRowCount( prevCount + len(newRows) )
        
        for i, data in enumerate(newRows, prevCount):
            self.addRow( i, *data )
        
        self.autoSave()

    # File io ----

    def autoSave(self):
        '''
        Saves the current preset json file.
        '''
        path = os.path.expandvars(self.presetFilepath)
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        
        newData = self.convertNodesToNames()
        with open(path, 'w') as fid:
            json.dump(newData, fid, indent=4)

                
    def convertNodesToNames(self):
        '''
        Returns an json serializable version of the current preset file.
        '''
        convertedMaster = collections.OrderedDict()
        for presetName, preset in self.profiles.items():
            converted = collections.OrderedDict()
            for ctrl, space in preset.items():
                ctrlName = simpleName(ctrl) if not isinstance(ctrl, basestring) else ctrl
                
                converted[ctrlName] = space
            convertedMaster[presetName] = converted
            
        return convertedMaster



def profileNamePrompt(msg='Enter a name', name='', validator=lambda x: True):
    '''
    validator is a function that takes the name and returns a string of the new message to display.
    '''
    
    while True:
        res = promptDialog(m=msg, t='Enter a profile name', tx=name, b=['Enter', 'Cancel'])
        if res == 'Cancel':
            return None
        
        name = promptDialog(q=True, text=True)
        
        temp = validator(name)
        if temp is not None:
            msg = temp
        else:
            return name


def isValidFilename(name):
    res = re.search( '[\w -_\.]*', name )
    if res:
        return res.group(0) == name
    
    return False


class AddPresetDialog(QtWidgets.QDialog):
    def __init__(self, locations, parent=None):
        super(AddPresetDialog, self).__init__()
        
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        self.ui.location.addItems( locations )
    
        self.ui.ok.clicked.connect( self.validate )
        self.ui.cancel.clicked.connect( self.reject )


    def presetNameExists(self, name):
        folder = SpacePresets.presetLocations[ self.ui.location.currentText() ]
        return name.lower() in {f.lower() for f in os.listdir(folder)}
    
    
    def validate(self):
        name = self.ui.nameEntry.text()
        if not name:
            self.ui.message.setText( '** You must specify a name! **' )
            return
            
        elif self.presetNameExists(name):
            self.ui.message.setText( '** This name already exists, choosea new one **' )
            return
            
        elif not isValidFilename(name):
            self.ui.message.setText( '** This name must be a valid filename **' )
            return

        self.accept()


def getLimbKeyTimes(control, start, end):
    '''
    If there are any keys at all, they are returned, including the start/end (if given).
    '''
    #otherObj = control.getOtherMotionType()
    
    #drivePlug = controllerShape.getSwitcherPlug(control)

    controls = [ ctrl for name, ctrl in control.subControl.items() ] + [control]
    
    finalRange = lib.anim.findKeyTimes(controls, start=start, end=end)
    
    return finalRange


def getIkSwitchCommand(ikController):
    ikControl = fossil.rig.getMainController(ikController)
    
    # Determine what type of switching to employ.
    card = ikControl.card
    
    if card.rigCommand == 'DogHindleg':
        switchCmd = fossil.kinematicSwitch.ActivateIkDispatch.activate_dogleg

    elif card.rigCommand in ['SplineChest', 'SplineChestV2']:
        switchCmd = fossil.kinematicSwitch.ActivateIkDispatch.active_splineChest

    elif card.rigCommand == 'SplineNeck':
        switchCmd = fossil.kinematicSwitch.ActivateIkDispatch.active_splineNeck
    else:
        switchCmd = fossil.kinematicSwitch.ActivateIkDispatch.active_ikChain

    ikControls = [ctrl for name, ctrl in ikControl.subControl.items()] + [ikControl]
    
    switcherPlug = fossil.controllerShape.getSwitcherPlug(ikControl)
    
    def cmd():
        switchCmd(ikControl)
        #setAttr(switcherPlug, 1)
        setKeyframe(switcherPlug, v=1)
        #if key:
        setKeyframe(ikControls, shape=False)
    
    return cmd


def getSpaceTimes(control, range=(None, None)):
    ''' Returns the times a space is keyed on the given control. '''
    attrs = ['space'] + [t + a for t in 'tr' for a in 'xyz']
    
    times = keyframe( control, at=attrs, q=True, tc=True)
    times = sorted(set(times))
    if range[0] is not None and range[1] is not None:
        times = [ t for t in times if range[0] <= t <= range[1] ]
    elif range[0]:
        times = [ t for t in times if range[0] <= t ]
    elif range[1]:
        times = [ t for t in times if t <= range[1] ]
    
    return times


def performSpaceSwitch(control, targetSpace, enumVal):
    
    # Skip if already in the correct space
    if control.space.get() == enumVal:
        return
    
    presetLog.debug( 'Switching {} to {}'.format(control, targetSpace) )
    fossil.space.switchToSpace( control, targetSpace )
    
    control.space.setKey()
    control.t.setKey()
    control.r.setKey()


def toFk(ctrls, switcher):
    '''
    Args:
        ctrls: list of fk controls to be activated, with the main control listed first
    '''
    fossil.kinematicSwitch.activateFk( ctrls[0] )
    
    setKeyframe(ctrls, shape=False)
    
    setKeyframe(switcher)


def shouldBeFk(mainCtrl, switcher):
    return (mainCtrl.getMotionType().endswith('fk') and getAttr(switcher) != 0.0)
                        

def shouldBeIk(mainCtrl, switcher):
    return (not mainCtrl.getMotionType().endswith('fk') and getAttr(switcher) != 1.0)


def cleanTargetKeys(mainCtrl, switcher, times):
    '''
    Make sure the switcher is keyed at all the given times and the controls are unkeyed.
    
    *Technically* this should leave keys when it's keyed on, but this is already so complicated.
    
    '''
    if times:
        # If we are range switching, we have to key everything.
            
        # Put keys at all frames that will be switched if not already there to anchor the values.
        # Only doing a single key because `insert=True` keying is done later
        if not keyframe(switcher, q=True):
            setKeyframe(switcher, t=times[0])
        
        allControls = [ctrl for name, ctrl in mainCtrl.subControl.items()] + [mainCtrl]
        # Remove all the old keys EXCLUDING SHAPES to preserve switches
        cutKey( allControls, iub=True, t=(times[0], times[-1]), clear=True, shape=False )
            
        for t in times:
            setKeyframe( switcher, t=t, insert=True )


def apply(preset, mode):
    '''
    &&& Do I optionally bookend the ranged switches?  Probably.
    Args:
        preset: Dict of { <pynode control>: '<space name or "# Activate">', ... }
        mode: str of [frame, all, range, selected]
    '''
    
    '''
    Tests
    All the combinations:
        Fk to Ik, ends are keyed
            opposite
        Fk to Ik, ends are not keyed
            opposite
        
    '''
    
    if mode == 'frame':
        # Single frame is easy, just do the work and get out
        for ctrl, targetSpace in preset.items():
            mainCtrl = fossil.rig.getMainController(ctrl)
            switcher = fossil.controllerShape.getSwitcherPlug(ctrl)
            
            # Ensure we're in ik or fk prior to switching spaces
            if switcher:
                if shouldBeFk(mainCtrl, switcher):
                    fossil.kinematicSwitch.activateFk( mainCtrl )
                elif shouldBeIk(mainCtrl, switcher):
                    getIkSwitchCommand(mainCtrl)()
            
            # Finally space switch
            if targetSpace != ACTIVATE_KEY:
                fossil.space.switchToSpace( ctrl, targetSpace )
        
        return
        
    else:
        if mode == 'all':
            keyRange = (None, None)
        elif mode == 'range':
            keyRange = (playbackOptions(q=True, min=True), playbackOptions(q=True, max=True))
        elif mode == 'selected':
            if not core.time.rangeIsSelected():
                keyRange = [currentTime()] * 2
            else:
                keyRange = core.time.selectedTime()

        presetLog.debug('Range {} {}'.format(keyRange[0], keyRange[-1]))
        
        '''
        This is a complex optimization.  The naive switcher ran over the timeline for _each_ control.
        Walking the timeline is the slowest operation (probably because all other nodes update) so a 10 control
        profile took 10x longer than a 1 control profile.
        
        Solution: collect all the times all events occur at, walk the timeline ONCE and switch as needed.
        Technically this is actually done twice, once to do the kinematic switch, and again to for the space.
        Future improvement will try to do it as one.
        
        kinematicSwitches[ <switch command> ] = [ <list of times to run at> ]
        
        
        '''
        
        kinematicSwitches = {}
        allTimes = set()
        
        for ctrl, targetSpace in preset.items():
            if isinstance(ctrl, basestring):
                continue
                
            mainCtrl = fossil.rig.getMainController(ctrl)
            switcher = fossil.controllerShape.getSwitcherPlug(ctrl)

            # Implicit to ensure we're in the mode that the space is in.
            if switcher:
                times = getLimbKeyTimes( mainCtrl.getOtherMotionType(), keyRange[0], keyRange[1] )
                if shouldBeFk(mainCtrl, switcher):
                    
                    if not times and mode == 'all':
                        # I think we can just switch since it's unkeyed and move on
                        if switcher:
                            if shouldBeFk(mainCtrl, switcher):
                                fossil.kinematicSwitch.activateFk( mainCtrl )
                            elif shouldBeIk(mainCtrl, switcher):
                                getIkSwitchCommand(mainCtrl)()
                                
                    else:
                        presetLog.debug( 'Switch to FK {}: {} - {}'.format(mainCtrl, times[0], times[-1]) )
                        fkCtrls = [mainCtrl] + [ctrl for name, ctrl in mainCtrl.subControl.items()]
                        
                        kinematicSwitches[ partial(toFk, fkCtrls, switcher) ] = times
                        allTimes.update( times )
                    
                elif shouldBeIk(mainCtrl, switcher):
                    presetLog.debug( 'Switch to IK {} {} - {}'.format(mainCtrl, times[0], times[-1]) )
                    times = getLimbKeyTimes( mainCtrl.getOtherMotionType(), keyRange[0], keyRange[1] )
                    kinematicSwitches[ getIkSwitchCommand(mainCtrl) ] = times
                    allTimes.update( times )
                                
                cleanTargetKeys(mainCtrl, switcher, times)
        
        with core.time.PreserveCurrentTime():
            # First timeline runthrough - ensure the kinematic state is correct.
            with core.ui.NoUpdate():
                presetLog.debug('KINEMATIC TIMES {}'.format(allTimes))
                for i in sorted(allTimes):
                    currentTime(i)
                    for cmd, vals in kinematicSwitches.items():
                        if i in vals:
                            cmd()
            
            # Just like with kinematics, gather all the frames a space switch is needed.
            spaceSwitches = {}
            
            allSpaceTimes = set()
            for ctrl, targetSpace in preset.items():
                if not isinstance(ctrl, basestring) and targetSpace != ACTIVATE_KEY:
                    
                    # If the space is unkeyed, just switch it, other wise store it
                    times = getSpaceTimes(ctrl, keyRange)
                    if not times:
                        fossil.space.switchToSpace( ctrl, targetSpace )
                    else:
                        allSpaceTimes.update(times)
                    
                        presetLog.debug('Switch Ctrl {}'.format(ctrl) )
                        enumVal = ctrl.space.getEnums()[targetSpace]
                        spaceSwitches[ partial(performSpaceSwitch, ctrl, targetSpace, enumVal) ] = times
            
            # Finally, walk the timeline a second time switching spaces as needed.
            with core.ui.NoUpdate():
                for i in sorted(allSpaceTimes):
                    currentTime(i)
                    for cmd, vals in spaceSwitches.items():
                        if i in vals:
                            cmd()