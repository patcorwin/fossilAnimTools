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
import json
import logging
import os
import re

from pymel.core import button, Callback, cmds, columnLayout, confirmDialog, currentTime, cutKey, deleteUI, fileDialog2, \
    frameLayout, formLayout, getAttr, keyframe, menu, menuBarLayout, menuItem, optionMenu, playbackOptions, promptDialog, rowColumnLayout, \
    select, selected, setKeyframe, scriptJob, scrollLayout, separator, showWindow, text, textScrollList, window, optionMenuGrp

from pdil.add import shortName, simpleName

from pdil import core
from pdil.tool import fossil

log = logging.getLogger(__name__)

try:
    basestring # noqa
except Exception:
    basestring = str


if '_previouslyLoaded' not in globals():
    _previouslyLoaded = None

ACTIVATE_KEY = '# Activate'


class SpacePresets(object):
    
    name = 'SpacePresets'
    menuWidth = 120
    labelWidth = 100
    leftSide = 300
    xWidth = 20

    #folders = [ 'C:/MAYA_APP_DIR/SpacePresets', '%RxArtToolRoot%/Maya/SpacePresets' ]
    folders = { 'local': os.environ['maya_app_dir'] + '/SpacePresets' }

    @classmethod
    @core.alt.name( 'Space Presets' )
    def run(cls):
        if window(cls.name, ex=True):
            deleteUI(cls.name)

        window(cls.name)
        menuBarLayout()
            
        content = SpacePresets()
        content.menu()

        showWindow()
        
        return content

    def menu(self):
        menu(l='File')
        menuItem(l='Save', c=Callback(self.save))
        menuItem(l='Load', c=Callback(self.load))

    def __init__(self):
        global _previouslyLoaded
        self.presets = {}
        self.curPreset = {}

        self.presetModificationUI = []
        
        self.filepath = ''

        mainForm = formLayout()

        self.mainForm = mainForm

        with columnLayout(adj=True) as self.mainLayout:
            with rowColumnLayout(nc=4):
                text(l='Current:  ')
                self.name = text(l='')
                self.location = text(l='')
                self.char = optionMenu(l='', cc=Callback(self.changeCharacter))
            
            self.presetModificationUI.append(button(l='Make Preset', c=Callback(self.makePreset)))

            separator(st='in')
            with rowColumnLayout(nc=3, cw=[(i, self.leftSide / 3 - 2) for i in range(1, 4)]):
                
                self.presetModificationUI += [
                    button(l='Rename', c=Callback(self.renamePreset)),
                    button(l='Delete', c=Callback(self.removePreset)),
                    button(l='Clone', c=Callback(self.clonePreset)) ]
            
            self.presetList = textScrollList(nr=9, sc=Callback(self.presetSelected))

            with frameLayout(l='Apply') as applyLayout:
                with rowColumnLayout(nc=4):
                    button(w=70, l='Frame', c=Callback(self.apply))
                    button(w=70, l='Playback', c=Callback(self.apply, 'range'))
                    button(w=70, l='All', c=Callback(self.apply, 'all'))
                    button(w=70, l='Selected', c=Callback(self.apply, 'selected'))

            self.presetModificationUI.append(applyLayout)
            
            with frameLayout(l='Loading', cll=True):

                self.presetLocationChooser = optionMenuGrp(l='Presets location', cc=self.setPresetLocation)
                for name in self.folders:
                    menuItem(l=name)
                
                #with rowColumnLayout(nc=2, cw=[(1, self.leftSide / 2), (2, self.leftSide / 2)]):
                with columnLayout(adj=True):
                    button(l='New', c=Callback(self.newCharacterPreset))
                    #self.localList = textScrollList(nr=5)
                    self.presetPaths = textScrollList(nr=5, sc=self.loadPreset)
                    
                #with columnLayout(adj=True):
                #    button(l='Public:   New', c=Callback(self.newCharacterPreset, 'public'))
                #    self.publicList = textScrollList(nr=5)
            
            self.refreshCharacterLists()

            # Technically these go with the stuff below but organizing ui in a formLayout is such a pain
            text(l=' ')
            button(l='Add Selected Control', c=Callback(self.grabSelected) )
            text(l='Control - Spaces')
            
        # Jumping through hoops to get the bottom section expanding with window.
        controlAssigner = scrollLayout(p=self.mainForm)
        self.controlLister = rowColumnLayout( p=controlAssigner,                     nc=3,
            cs=[(1, 10), (2, 10), (3, 14)],
            cw=[(1, self.labelWidth), (2, self.menuWidth), (3, self.xWidth)])
        
        formLayout(mainForm, e=True,
            af=[
                (self.mainLayout, 'left', 0),
                (self.mainLayout, 'right', 0),
                (self.mainLayout, 'top', 0),
                
                (controlAssigner, 'left', 0),
                (controlAssigner, 'right', 0),
                (controlAssigner, 'bottom', 0)
            ],
            
            ac=[
                (controlAssigner, 'top', 0, self.mainLayout),
            ]
        )
        
        for name in self.presets:
            self.presetList.append(name)
            
        self.disablePresetUI()
        
        scriptJob(e=['NewSceneOpened', self.clear], p=self.mainLayout)
        scriptJob(e=['SceneOpened', self.reload], p=self.mainLayout)
        
        # Handle opening the last thing
        self.reload()
    
    def setPresetLocation(self, locKey):
        pass
    
    def changeCharacter(self):
        index = self.char.getSelect() - 1  # One off indices
        self.presets = self.rankedPresets.items()[index][1]
        self.loadFormattedPreset()

    def clear(self):
        self.presets = {}
        self.curPreset = {}
        self.filepath = ''
        
        self.presetList.removeAll()
        self.clearControlSpaces()

    def reload(self):
        '''
        Opening a file will try to reload so the internal control mappings are
        correct.
        '''
        global _previouslyLoaded
        if _previouslyLoaded:
            if os.path.exists(_previouslyLoaded):
                self.clearControlSpaces()
                self._load(_previouslyLoaded)
            else:
                self.clear()
        else:
            self.clear()

    def loadPreset(self):
        presetLocKey = self.presetLocationChooser.getValue()
        folder = self.folders[ presetLocKey ]
        
        name = self.presetPaths.getSelectItem()[0]
        
        filename = folder + '/%s.json' % name
        
        print(os.path.exists(filename), filename, '-----')
        
        self._load( filename)

    def refreshCharacterLists(self):
        #def loadCharacters(folder, lister, location):
        #    folder = os.path.expandvars(folder)
        #    if not os.path.exists(folder):
        #        return
        #
        #    for f in os.listdir(folder):
        #        if f.lower().endswith('.json'):
        #            textScrollList(lister, e=True, a=f[:-5])
        #
        #    def loadPreset():
        #        sel = textScrollList(lister, q=True, si=True)
        #        if not sel:
        #            return
        #        self._load( folder + '/%s.json' % sel[0])
        #
        #    textScrollList(lister, e=True, sc=loadPreset)
        
        #textScrollList(self.localList, e=True, ra=True)
        #textScrollList(self.publicList, e=True, ra=True)
            
        #loadCharacters(self.folders[0], self.localList, 'local')
        #loadCharacters(self.folders[1], self.publicList, 'public')
        self.presetPaths.removeAll()
        
        presetLocKey = self.presetLocationChooser.getValue()
        
        folder = self.folders[ presetLocKey ]
        
        print('yes')
        
        if not os.path.exists(folder):
            return
            
        for f in os.listdir(folder):
            print('f----', f)
            if f.lower().endswith('.json'):
                print('yess')
                #textScrollList(self.presetPaths, e=True, a=f[:-5])
                self.presetPaths.append(f[:-5])


    def enablePresetUI(self):
        '''
        When a preset is loaded, the ui to modify it must be enabled.
        '''
        for ctrl in self.presetModificationUI:
            ctrl.setEnable(True)

    def disablePresetUI(self):
        '''
        When there is no preset loaded, disable the UI that modifies presets.
        '''
        for ctrl in self.presetModificationUI:
            ctrl.setEnable(False)

    def newCharacterPreset(self):
        locKey = self.presetLocationChooser.getValue()
        
        res = promptDialog(t='Character', m='What is the name of the character?')
        if res != 'Confirm' or not promptDialog(tx=True, q=True):
            return
        
        name = promptDialog(tx=True, q=True)
        
        path = self.folders[locKey]
        
        filename = path + '/' + name + '.json'
        
        if os.path.exists(filename):
            self._load(filename)
        else:
            self.presets = {}
            self.filepath = filename
            self.autoSave()
            self.setLoadedLabel()
            self.refreshCharacterLists()
            self.enablePresetUI()

    def makePreset(self):
        res = promptDialog(m='Name')
        if res != 'Confirm' or not promptDialog(tx=True, q=True):
            return

        name = promptDialog(tx=True, q=True)
        
        if name in self.presets:
            confirmDialog(m='A preset of that name already exists, choose another')
            return
        
        self.presets[name] = {}
        self.curPreset = self.presets[name]

        self.presetList.append(name)
        
        self.autoSave()
        
        self.presetList.setSelectItem(name)
        self.presetSelected()

    def clearControlSpaces(self):
        children = cmds.layout(self.controlLister.name(), q=True, ca=True)
        if children:
            deleteUI(children)

    def presetSelected(self):
        presetName = self.presetList.getSelectItem()[0]

        self.curPreset = self.presets[presetName]

        self.clearControlSpaces()

        for ctrl, space in sorted(self.curPreset.items()):
            if not isinstance(ctrl, basestring):
                try:
                    self.addRow(ctrl, space)
                except Exception:
                    text(l='Error :' + ctrl.name, p=self.controlLister.name())
                    text(l=space, p=self.controlLister.name())
                    text(l='', p=self.controlLister.name())
            else:
                text(l='NOT FOUND:' + ctrl, p=self.controlLister.name())
                text(l=space, p=self.controlLister.name())
                text(l='', p=self.controlLister.name())

    def renamePreset(self):
        try:
            presetName = self.presetList.getSelectItem()[0]
        except IndexError:
            return
            
        res = promptDialog(m='New Name', tx=presetName)
        newName = promptDialog(q=True, tx=True)
        if res == 'Confirm' and newName:
            if newName == presetName:
                return
            
            if newName in self.presets:
                confirmDialog(m='A preset of that name already exists, choose another')
                return
            
            self.presets[newName] = self.presets[presetName]
            del self.presets[presetName]
            self.presetList.removeItem(presetName)
            self.presetList.append(newName)
            self.clearControlSpaces()
            self.presetList.setSelectItem(newName)
            self.presetSelected()
            self.autoSave()
        
    def clonePreset(self):
        try:
            presetName = self.presetList.getSelectItem()[0]
        except IndexError:
            return
            
        res = promptDialog(m='New Name')
        newName = promptDialog(q=True, tx=True)
        if res == 'Confirm' and newName:
            if newName in self.presets:
                confirmDialog(m='A preset of that name already exists, choose another')
                return
            
            self.presets[newName] = copy.deepcopy(self.presets[presetName])
            
            self.presetList.append(newName)
            self.clearControlSpaces()
            self.presetList.setSelectItem(newName)
            self.presetSelected()
            self.autoSave()
        
    def removePreset(self):
        try:
            presetName = self.presetList.getSelectItem()[0]
        except IndexError:
            return
            
        del self.presets[presetName]
        self.presetList.removeItem(presetName)
        self.clearControlSpaces()
        self.presetList.deselectAll()
        self.autoSave()

    def grabSelected(self):
        try:
            presetName = self.presetList.getSelectItem()[0]
        except IndexError:
            return

        # Verify we have a control, with spaces, not already in the preset
        for obj in selected():
            names = fossil.space.getNames(obj)
            log.debug( 'Grabbing -- Obj: {}, names: {}'.format(obj, names) )
            
            motionOnly = False
            if not names:
                if not fossil.controllerShape.getSwitcherPlug(obj):
                    continue
                else:
                    motionOnly = True

            if obj in self.curPreset:
                continue

            # Finally add it to the preset, or '#' if it's a motion only switch
            if motionOnly:
                self.curPreset[obj] = ACTIVATE_KEY
            else:
                self.curPreset[obj] = fossil.space.get(obj)

            self.addRow(obj, self.curPreset[obj])
            
        self.autoSave()

    def removeControl(self, ctrl):
        try:
            del self.curPreset[ctrl]
            self.presetSelected()
            
            self.autoSave()
        except KeyError:
            pass

    def _select(self, ctrlName):
        select(ctrlName, add=core.keyModifier.control())

    def addRow(self, ctrl, spaceName):

        ctrlName = shortName(ctrl)
                
        cmds.button(l=ctrlName, p=self.controlLister.name(), w=self.menuWidth - 10, c=Callback(self._select, ctrlName))
        
        spaces = cmds.optionMenu(l='', p=self.controlLister.name(), w=self.menuWidth)
        for space in fossil.space.getNames(ctrl):
            cmds.menuItem(l=space)
        cmds.menuItem(l=ACTIVATE_KEY)
            
        cmds.optionMenu(spaces, e=True, v=spaceName, cc=partial(self.setSpace, ctrl) )
        
        cmds.button(l='X', p=self.controlLister.name(), c=Callback(self.removeControl, ctrl))

    def setSpace(self, ctrl, space):
        self.curPreset[ctrl] = space
        self.autoSave()

    def apply(self, mode='frame'):
        apply(self.curPreset, mode)
        '''
        if mode == 'frame':
            keyRange = [currentTime()]*2
        elif mode == 'all':
            keyRange = (None, None)
        elif mode == 'range':
            keyRange = (playbackOptions(q=True, min=True), playbackOptions(q=True, max=True))
        elif mode == 'selected':
            if not lib.anim.rangeIsSelected():
                keyRange = [currentTime()]*2
            else:
                keyRange = lib.anim.selectedTime()

        for ctrl, targetSpace in self.curPreset.items():
            if not isinstance(ctrl, basestring):
                fossil.space.switchRange(ctrl, targetSpace, range=keyRange)
        '''

    def autoSave(self):
        
        path = os.path.expandvars(self.filepath)
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        
        with open(path, 'w') as fid:
            json.dump(self._saveConvert(), fid, indent=4)

    def save(self):
        result = fileDialog2(fm=0, ff='Json(*.json)')
        if result:
            with open(result[0], 'w') as fid:
                json.dump(self._saveConvert(), fid, indent=4)
                
    def _saveConvert(self):
        # Turn PyNode control into shortNames
        convertedMaster = {}
        for presetName, preset in self.presets.items():
            converted = {}
            for ctrl, space in preset.items():
                if not isinstance(ctrl, basestring):
                    ctrlName = simpleName(ctrl)
                converted[ctrlName] = space
            convertedMaster[presetName] = converted
            
        return convertedMaster
        
    def load(self):
        result = fileDialog2(fm=1, ff='Json(*.json)')

        if result:
            self._load(result[0])
            
    def _load(self, filename):
        global _previouslyLoaded
        
        self.filepath = filename
        self.rankedPresets = load(filename)
        
        self.presets = self.rankedPresets.items()[0][1]
        
        items = optionMenu(self.char, q=True, ill=True)
        if items:
            deleteUI(items)
        
        self.char.addItems( [main for rank, main in self.rankedPresets] )
    
        self.loadFormattedPreset()
        
        _previouslyLoaded = filename
    
    def loadFormattedPreset(self):
        self.presetList.removeAll()
        for name in sorted(self.presets):
            self.presetList.append(name)
        
        self.enablePresetUI()
        self.setLoadedLabel()
    
    def setLoadedLabel(self):
        '''
        ..  todo::
            Use the path to determine the location instead of passing it around.
        '''
        name = os.path.splitext(os.path.basename( self.filepath ))[0]
        self.name.setLabel(name)
        self.location.setLabel( '  (' + self.presetLocationChooser.getValue() + ')' )
        

def load(filename):
    '''
    Given preset `filename`, returns a dict of the actual controls in the scene
    mapped to their spaces.
    
    ex:
    # File has:
    {
        'TrueWorld': {  'Arm_L': 'trueWorld',
                        'Leg_L_pv': 'trueWorld',
                        'Leg_R_pv': 'trueWorld'},
                        
        'World': {      'Arm_L': 'world',
                        'Leg_L_pv': 'world',
                        'Leg_R_pv': 'world'}
    }
    
    Turns into:
    {
        (0, 'Rig:Naga:main'):  # Number is how many unique controls failed to match
        {
            'TrueWorld': {  nt.RigController('Arm_L'): 'trueWorld',
                            nt.SubController('Leg_L_pv'): 'trueWorld',
                            nt.SubController('Leg_R_pv'): 'trueWorld'},
                            
            'World': {      nt.RigController('Arm_L'): 'world',
                            nt.SubController('Leg_L_pv'): 'world',
                            nt.SubController('Leg_R_pv'): 'world'}
        },
        (1, 'Griffin:Naga:main'):
        {
            'TrueWorld': {  nt.RigController('Arm_L'): 'trueWorld',
                            nt.SubController('Leg_L_pv'): 'trueWorld',
                            nt.SubController('Leg_R_pv'): 'trueWorld'},
                            
            'World': {      nt.RigController('Arm_L'): 'world',
                            nt.SubController('Leg_L_pv'): 'world',
        }
    }
    
    
    '''
    
    # Quick way to make a resetting cache for controllers()
    allControls = core.findNode.controllers()
    #allControlShortNames = [ simpleName(ctrl) for ctrl in allControls ]
    
    # Group all the controls by their main node.
    groups = {None: {}}
    mainNodePattern = re.compile('.*(\||:)main\|')
    for ctrl in allControls:
        match = mainNodePattern.match(ctrl.longName())
        if match:
            #print match.group(0)
            if match.group(0) not in groups:
                groups[match.group(0)] = {}
            
            groups[match.group(0)][simpleName(ctrl)] = ctrl
        else:
            groups[None][simpleName(ctrl)] = ctrl
    #print '\n'.join([str(s) for s in groups.keys()])
    #self.presetList.removeAll()
    
    with open(filename, 'r') as fid:
        rawPresets = json.load(fid)

    # Find all the controls that this set references
    requiredNames = set()
    for preset in rawPresets.values():
        for ctrlName in preset:
            requiredNames.add(ctrlName)
    
    # Find how many controls in the scene don't exist in each group
    ranked = []
    for main, shortNames in groups.items():
        if requiredNames.issubset( shortNames ):
            ranked.append( (len(requiredNames.difference(shortNames)), main) )
        
    # Turn the group's names in pynodes
    convertedMasters = collections.OrderedDict()

    for rank, main in sorted(ranked):
        # Turn all the control names into pynodes
        
        def getControl(short_name):
            if short_name in groups[main]:
                return groups[main][short_name]
            return None
        
        convertedMaster = {}
        for presetName, preset in rawPresets.items():
            converted = {}
            for ctrlName, space in preset.items():
                ctrl = getControl(ctrlName)
                if not ctrl:
                    ctrl = ctrlName
                converted[ctrl] = space
        
            convertedMaster[presetName] = converted
        
        convertedMasters[(rank, main)] = convertedMaster
            
    return convertedMasters
    
    
def apply_OLD(preset, mode):
    '''
    
    :test:
        # Make a leg, animate it in fk, apply and verify
        preset = {'Leg_L': 'world'}
    
    '''
    with core.ui.NoUpdate():
        if mode == 'frame':
            keyRange = [currentTime()] * 2
        elif mode == 'all':
            keyRange = (None, None)
        elif mode == 'range':
            keyRange = (playbackOptions(q=True, min=True), playbackOptions(q=True, max=True))
        elif mode == 'selected':
            if not core.time.rangeIsSelected():
                keyRange = [currentTime()] * 2
            else:
                keyRange = core.time.selectedTime()

        # Switch all explicit ik/fks

        for ctrl, targetSpace in preset.items():
            if not isinstance(ctrl, basestring):
                # Figure out if I'm in the right space
                mainCtrl = fossil.rig.getMainController(ctrl)
                
                switcher = fossil.controllerShape.getSwitcherPlug(ctrl)
                
                # Implicit to ensure we're in the mode that the space is in.
                if switcher:
                    if mainCtrl.getMotionType().endswith('fk') and getAttr(switcher) != 0.0:
                        fossil.kinematicSwitch.activateFkRange(mainCtrl, *keyRange)
                        
                    elif getAttr(switcher) != 1.0:
                        fossil.kinematicSwitch.activateIk(mainCtrl, *keyRange)
                
                if targetSpace != ACTIVATE_KEY:
                    fossil.space.switchRange(ctrl, targetSpace, range=keyRange)



def getLimbKeyTimes(control, start, end):
    #otherObj = control.getOtherMotionType()
    
    #drivePlug = controllerShape.getSwitcherPlug(control)

    controls = [ ctrl for name, ctrl in control.subControl.items() ] + [control]
    
    finalRange = core.time.findKeyTimes(controls, start=start, end=end)
    
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
    attrs = ['space'] + [t + a for t in 'tr' for a in 'xyz']
    #curTime = currentTime(q=True)
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

#getSpaceTimes(selected()[0])

#getLimbKeyTimes( selected()[0], 0, 30 )


presetLog = logging.getLogger('presetSwitching')
presetLog.setLevel( logging.DEBUG )


def toFk(ctrls, switcher):
    fossil.kinematicSwitch.activateFk( ctrls[0] )
    
    setKeyframe(ctrls, shape=False)
    
    setKeyframe(switcher)


def apply(preset, mode):
    if mode == 'frame':
        keyRange = [currentTime()] * 2
    elif mode == 'all':
        keyRange = (None, None)
    elif mode == 'range':
        keyRange = (playbackOptions(q=True, min=True), playbackOptions(q=True, max=True))
    elif mode == 'selected':
        if not core.time.rangeIsSelected():
            keyRange = [currentTime()] * 2
        else:
            keyRange = core.time.selectedTime()

    presetLog.debug('Range {} {}'.format(keyRange[0], keyRange[-1]))
    
    kinematicSwitches = {}
    allTimes = set()
    
    for ctrl, targetSpace in preset.items():
        if not isinstance(ctrl, basestring):
            mainCtrl = fossil.rig.getMainController(ctrl)
            switcher = fossil.controllerShape.getSwitcherPlug(ctrl)
            
            # Implicit to ensure we're in the mode that the space is in.
            if switcher:
                if (mainCtrl.getMotionType().endswith('fk') and getAttr(switcher) != 0.0):
                    times = getLimbKeyTimes( mainCtrl.getOtherMotionType(), keyRange[0], keyRange[1] )
                    
                    presetLog.debug( 'Switch to FK {} {} - {}'.format(mainCtrl, times[0], times[-1]) )
                    
                    fkCtrls = [mainCtrl] + [ctrl for name, ctrl in mainCtrl.subControl.items()]
                    
                    kinematicSwitches[ partial(toFk, fkCtrls, switcher) ] = times
                    
                    allTimes.update( times )
                    
                elif (not mainCtrl.getMotionType().endswith('fk') and getAttr(switcher) != 1.0):
                    times = getLimbKeyTimes( mainCtrl.getOtherMotionType(), keyRange[0], keyRange[1] )
                    kinematicSwitches[ getIkSwitchCommand(mainCtrl) ] = times
                    allTimes.update( times )
                    
                    presetLog.debug( 'Switch to IK {} {} - {}'.format(mainCtrl, times[0], times[-1]) )
                
                else:
                    times = []
                
                if len(times) > 1:
                    # If we are range switching, we have to key everything.
                        
                    # Put keys at all frames that will be switched if not already there to anchor the values
                    if not keyframe(switcher, q=True):
                        setKeyframe(switcher, t=times[0])
                    
                    ikControls = [ctrl for name, ctrl in mainCtrl.subControl.items()] + [mainCtrl]
                    # Remove all the old keys EXCLUDING SHAPES to preserve switches
                    cutKey( ikControls, iub=True, t=(times[0], times[-1]), clear=True, shape=False )
                        
                    for t in times:
                        setKeyframe( switcher, t=t, insert=True )
            
            #fossil.space.switchRange(ctrl, targetSpace, range=keyRange)
    
    with core.time.PreserveCurrentTime():
        with core.ui.NoUpdate():
            presetLog.debug('KIN TIMES {}'.format(allTimes))
            for i in sorted(allTimes):
                currentTime(i)
                for cmd, vals in kinematicSwitches.items():
                    if i in vals:
                        cmd()
        
        spaceSwitches = {}
        
        allTimes = set()
        for ctrl, targetSpace in preset.items():
            if not isinstance(ctrl, basestring):
                
                times = getSpaceTimes(ctrl, keyRange)
                if not times:
                    fossil.space.switchToSpace( ctrl, targetSpace )
                else:
                    allTimes.update(times)
                
                presetLog.debug('Switch Ctrl {}'.format(ctrl) )
                enumVal = ctrl.space.getEnums()[targetSpace]
                spaceSwitches[ partial(performSpaceSwitch, ctrl, targetSpace, enumVal) ] = times
        
        with core.ui.NoUpdate():
            for i in sorted(allTimes):
                currentTime(i)
                for cmd, vals in spaceSwitches.items():
                    if i in vals:
                        cmd()