from pymel.core import button, Callback, columnLayout, currentTime, intField, keyframe, ls, \
    radioButtonGrp, rowColumnLayout, selected


import pdil
from pdil.tool import fossil


offsetCurveOptions = pdil.ui.Settings(
    'offsetCurveOptions',
    {
        'wholeRange': False,
        'bookend': False,
        'uiMode': 1,
    }
)

        
class OffsetCurvesGui(object):
    id = 'OffsetCurves'

    @staticmethod
    @pdil.alt.name('Offset Curves Gui')
    def show():
        return OffsetCurvesGui()
        
    def __init__(self):
        global offsetCurveOptions
        
        with pdil.ui.singleWindow(self.id):
            with columnLayout():
                self.mode = radioButtonGrp(
                    nrb=3,
                    la3=['Playback Range', 'User Defined', 'All'],
                    on1=Callback(self.setPlaybackMode),
                    on2=Callback(self.setUserMode),
                    on3=Callback(self.setAllMode),
                )
                
                with rowColumnLayout(nc=2) as self.range:
                    self.start = intField()
                    self.end = intField()
            
                with rowColumnLayout(nc=2):
                    #checkBox(l='Autokey', en=False)
                    button(label='Apply', c=Callback(self.apply))

            if offsetCurveOptions.uiMode == 1:
                self.setPlaybackMode()
            elif offsetCurveOptions.uiMode == 2:
                self.setUserMode()
            elif offsetCurveOptions.uiMode == 3:
                self.setAllMode()
    
    
    def apply(self):
        global offsetCurveOptions
        if self.mode.getSelect() == 1:
            _range = None
            offsetCurveOptions.wholeRange = False
    
        elif self.mode.getSelect() == 2:
            _range = self.start.getValue(), self.end.getValue()
            
        elif self.mode.getSelect() == 3:
            _range = None
            offsetCurveOptions.wholeRange = True
        
        offsetCurves(_range)
        
    def setPlaybackMode(self):
        self.range.setEnable(False)
        self.mode.setSelect(1)
        offsetCurveOptions.uiMode = 1
        
    def setUserMode(self):
        self.range.setEnable(True)
        self.mode.setSelect(2)
        offsetCurveOptions.uiMode = 2
    
    def setAllMode(self):
        self.range.setEnable(False)
        self.mode.setSelect(3)
        offsetCurveOptions.uiMode = 3
        
        
@pdil.alt.name('Offset Curves')
def offsetCurves(_range=None):
    global offsetCurveOptions
    
    objs = []
    
    sel = selected()
    controllers = fossil.find.controllers()
    
    # Try to determine what objects to operate on
    if sel:
        # Not sure what I was trying to do here, maybe offsetting for the
        # selected character?  Regardless, it doesn't work so just run on selection
        #if sel[0] in controllers:
            #objs = controllers
        #else:
        objs = sel
    else:
        objs = controllers
        
    if not _range:
        if pdil.time.rangeIsSelected():
            start, end = pdil.time.selectedTime()
        elif offsetCurveOptions.wholeRange:
            start, end = (None, None)
        else:
            start, end = pdil.time.playbackRange()
    else:
        start, end = _range
    
    objs = ls(objs, type='transform')
    
    for obj in objs:
        if offsetCurveOptions.bookend:
            pass
        offsetObj( obj, (start, end) )
        
        
def offsetObj(obj, _range=(None, None)):
    '''
    Given an object, adjusts it's curves to by the amount from the current place.
    '''
    
    now = currentTime(q=True)
    
    adjust = []
    for attr in [ t + a for t in 'trs' for a in 'xyz' ]:
        cur = obj.attr(attr).get()
        keyed = obj.attr(attr).get(time=now)
        if cur != keyed:
            adjust.append( (attr, cur - keyed ) )
    
    timeArg = {'t': _range} if _range != (None, None) else {}
    
    for attr, delta in adjust:
        keyframe(obj.attr(attr), e=True, iub=True, r=True, vc=delta, **timeArg)