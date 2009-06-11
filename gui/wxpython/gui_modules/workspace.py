"""!
@package workspace.py

@brief Open/save workspace definition file

Classes:
 - ProcessWorkspaceFile
 - Nviz
 - WriteWorkspaceFile
 - ProcessGrcFile

(C) 2007-2009 by the GRASS Development Team
This program is free software under the GNU General Public
License (>=v2). Read the file COPYING that comes with GRASS
for details.

@author Martin Landa <landa.martin gmail.com>
"""

import os
import sys

import wx

### for gxw (workspace file) parsering
# xmlproc not available on Mac OS
# from xml.parsers.xmlproc import xmlproc
# from xml.parsers.xmlproc import xmlval
# from xml.parsers.xmlproc import xmldtd
try:
    import xml.etree.ElementTree as etree
except ImportError:
    import elementtree.ElementTree as etree # Python <= 2.4

import utils
import globalvar
from preferences import globalSettings as UserSettings

sys.path.append(os.path.join(globalvar.ETCWXDIR, "nviz"))
try:
    import grass7_wxnviz as wxnviz
except ImportError:
    wxnviz = None

class ProcessWorkspaceFile():
    def __init__(self, tree):
        """!A ElementTree handler for the GXW XML file, as defined in
        grass-gxw.dtd.
        """
        self.tree = tree
        self.root = self.tree.getroot()
        
        #
        # layer manager properties
        #
        self.layerManager = {}
        self.layerManager['pos']  = None # window position
        self.layerManager['size'] = None # window size
        
        #
        # list of mapdisplays
        #
        self.displays = []
        #
        # list of map layers
        #
        self.layers = []
        
        self.displayIndex = -1 # first display has index '0'
        
        self.__processFile()
        
        self.nvizDefault = Nviz()
        
    def __filterValue(self, value):
        """!Filter value
        
        @param value
        """
        value = value.replace('&lt;', '<')
        value = value.replace('&gt;', '>')
        
        return value

    def __getNodeText(self, node, tag, default = ''):
        """!Get node text"""
        p = node.find(tag)
        if p is not None:
            return utils.normalize_whitespace(p.text)
        
        return default
    
    def __processFile(self):
        """!Process workspace file"""
        #
        # layer manager
        #
        node_lm = self.root.find('layer_manager')
        if node_lm is not None:
            posAttr = node_lm.get('dim', '')
            if posAttr:
                posVal = map(int, posAttr.split(','))
                try:
                    self.layerManager['pos']  = (posVal[0], posVal[1])
                    self.layerManager['size'] = (posVal[2], posVal[3])
                except:
                    pass
        
        #
        # displays
        #
        for display in self.root.findall('display'):
            self.displayIndex += 1
            
            # window position and size
            posAttr = display.get('dim', '')
            if posAttr:
                posVal = map(int, posAttr.split(','))
                try:
                    pos  = (posVal[0], posVal[1])
                    size = (posVal[2], posVal[3])
                except:
                    pos  = None
                    size = None
            else:
                pos  = None
                size = None
            
            extentAttr = display.get('extent', '')
            if extentAttr:
                # w, s, e, n
                extent = map(float, extentAttr.split(','))
            else:
                extent = None
            
            self.displays.append( {
                    "render"         : bool(int(display.get('render', "0"))),
                    "mode"           : int(display.get('mode', 0)),
                    "showCompExtent" : bool(int(display.get('showCompExtent', "0"))),
                    "pos"            : pos,
                    "size"           : size,
                    "extent"         : extent,
                    "constrainRes"   : bool(int(display.get('constrainRes', "0"))) } )
            
            # process all layers/groups in the display
            self.__processLayers(display)

    def __processLayers(self, node):
        """!Process layers/groups of selected display

        @todo Fix group flag
        
        @param node display tree node
        """
        for item in node.getchildren():
            if item.tag == 'group':
                # -> group
                self.layers.append( {
                        "type"    : 'group',
                        "name"    : item.get('name', ''),
                        "checked" : bool(int(item.get('checked', "0"))),
                        "opacity" : None,
                        "cmd"     : None,
                        "group"   : False, #### self.inTag['group'], # ???
                        "display" : self.displayIndex,
                        "nviz"    : None})
                
            elif item.tag == 'layer':
                cmd, selected, nviz = self.__processLayer(item)
                
                self.layers.append( {
                        "type"     : item.get('type', None),
                        "name"     : item.get('name', None),
                        "checked"  : bool(int(item.get('checked', "0"))),
                        "opacity"  : float(item.get('opacity', '1.0')),
                        "cmd"      : cmd,
                        "group"    : False, #### self.inTag['group'], # ???
                        "display"  : self.displayIndex,
                        "selected" : selected,
                        "nviz"     : nviz } )
        
    def __processLayer(self, layer):
        """!Process layer item

        @param layer tree node
        """
        cmd = list()
        
        #
        # layer attributes (task) - 2D settings
        #
        node_task = layer.find('task')
        cmd.append(node_task.get('name', "unknown"))
        
        # flags
        flags = ''
        for p in node_task.findall('flag'):
            flags += p.get('name', '')
        cmd.append('-' + flags)
        
        # parameters
        for p in node_task.findall('parameter'):
            cmd.append('%s=%s' % (p.get('name', ''),
                                  self.__filterValue(self.__getNodeText(p, 'value'))))
        
        if layer.find('selected') is not None:
            selected = True
        else:
            selected = False
        
        #
        # Nviz (3D settings)
        #
        node_nviz = layer.find('nviz')
        if node_nviz is not None:
            nviz = self.__processLayerNviz(node_nviz)
        else:
            nviz = None
        
        return (cmd, selected, nviz)

    def __processLayerNviz(self, node_nviz):
        """!Process 3D layer settings

        @param node_nviz nviz node
        """
        # init nviz layer properties
        nviz = {}
        if node_nviz.find('surface') is not None: # -> raster
            nviz['surface'] = {}
            for sec in ('attribute', 'draw', 'mask', 'position'):
                nviz['surface'][sec] = {}
        elif node_nviz.find('vlines') is not None or \
                node_nviz.find('vpoints') is not None: # -> vector
            nviz['vector'] = {}
            for sec in ('lines', 'points'):
                nviz['vector'][sec] = {}
        
        if nviz.has_key('surface'):
            node_surface = node_nviz.find('surface')
            # attributes
            for attrb in node_surface.findall('attribute'):
                tagName = str(attrb.tag)
                attrbName = attrb.get('name', '')
                dc = nviz['surface'][tagName][attrbName] = {}
                if attrb.get('map', '0') == '0':
                    dc['map'] = False
                else:
                    dc['map'] = True
                value = self.__getNodeText(attrb, 'value')
                try:
                    dc['value'] = int(value)
                except ValueError:
                    try:
                        dc['value'] = float(value)
                    except ValueError:
                        dc['value'] = str(value)
            
            # draw
            node_draw = node_surface.find('draw')
            if node_draw is not None:
                tagName = str(node_draw.tag)
                nviz['surface'][tagName]['all'] = False
                nviz['surface'][tagName]['mode'] = {}
                nviz['surface'][tagName]['mode']['value'] = -1 # to be calculated
                nviz['surface'][tagName]['mode']['desc'] = {}
                nviz['surface'][tagName]['mode']['desc']['shading'] = \
                    str(node_draw.get('shading', ''))
                nviz['surface'][tagName]['mode']['desc']['style'] = \
                    str(node_draw.get('style', ''))
                nviz['surface'][tagName]['mode']['desc']['mode'] = \
                    str(node_draw.get('mode', ''))
                
                # resolution
                for node_res in node_draw.findall('resolution'):
                    resType = str(node_res.get('type', ''))
                    if not nviz['surface']['draw'].has_key('resolution'):
                        nviz['surface']['draw']['resolution'] = {}
                    value = int(self.__getNodeText(node_res, 'value'))
                    nviz['surface']['draw']['resolution'][resType] = value
                
                # wire-color
                node_wire_color = node_draw.find('wire_color')
                if node_wire_color is not None:
                    nviz['surface']['draw']['wire-color'] = {}
                    value = str(self.__getNodeText(node_wire_color, 'value'))
                    nviz['surface']['draw']['wire-color']['value'] = value
                
            # position
            node_pos = node_surface.find('position')
            if node_pos is not None:
                dc = self.nviz['surface']['position'] = {}
                for coor in ['x', 'y', 'z']:
                    node = node_pos.find(coor)
                    if node is None:
                        continue
                    value = int(self.__getNodeText(node, 'value'))
                    dc[coor] = value
            
        elif nviz.has_key('vector'):
            # vpoints
            node_vpoints = node_nviz.find('vpoints')
            if node_vpoints is not None:
                marker = str(node_vpoints.get('marker', ''))
                markerId = list(UserSettings.Get(group='nviz', key='vector',
                                                 subkey=['points', 'marker'], internal=True)).index(marker)
                nviz['vector']['points']['marker'] = markerId
                
                node_mode = node_vpoints.find('mode')
                if node_mode is not None:
                    nviz['vector']['points']['mode'] = {}
                    nviz['vector']['points']['mode']['type'] = str(node_mode.get('type', ''))
                    nviz['vector']['points']['mode']['surface'] = ''
                    
                    # map
                    nviz['vector']['points']['mode']['surface'] = \
                        self.__processLayerNvizNode(node_vpoints, 'map', str)
                
                # color
                self.__processLayerNvizNode(node_vpoints, 'color', str,
                                            nviz['vector']['points'])
                
                # width
                self.__processLayerNvizNode(node_vpoints, 'width', int,
                                            nviz['vector']['points'])
                
                # height
                self.__processLayerNvizNode(node_vpoints, 'height', int,
                                            nviz['vector']['points'])
                
                # height
                self.__processLayerNvizNode(node_vpoints, 'size', int,
                                            nviz['vector']['points'])
            
            # vlines
            node_vlines = node_nviz.find('vlines')
            if node_vlines is not None:
                node_mode = node_vlines.find('mode')
                if node_mode is not None:
                    nviz['vector']['lines']['mode'] = {}
                    nviz['vector']['lines']['mode']['type'] = str(node_mode.get('type', ''))
                    nviz['vector']['lines']['mode']['surface'] = ''
                    
                    # map
                    nviz['vector']['lines']['mode']['surface'] = \
                        self.__processLayerNvizNode(node_mode, 'map', str)
                
                # color
                self.__processLayerNvizNode(node_vlines, 'color', str,
                                            nviz['vector']['lines'])
                
                # width
                self.__processLayerNvizNode(node_vlines, 'width', int,
                                            nviz['vector']['lines'])
                
                # height
                self.__processLayerNvizNode(node_vlines, 'height', int,
                                            nviz['vector']['lines'])
            
        return nviz
    
    def __processLayerNvizNode(self, node, tag, cast, dc = None):
        """!Process given tag nviz/vector"""
        node_tag = node.find(tag)
        if node_tag is not None:
            value = cast(self.__getNodeText(node_tag, 'value'))
            if dc:
                dc[tag] = dict()
                dc[tag]['value'] = value
            else:
                return value
    
class Nviz:
    def __init__(self):
        """Default 3D settings"""
        pass
    
    def SetSurfaceDefaultProp(self):
        """Set default surface data properties"""
        data = dict()
        for sec in ('attribute', 'draw', 'mask', 'position'):
            data[sec] = {}
        
        #
        # attributes
        #
        for attrb in ('shine', ):
            data['attribute'][attrb] = {}
            for key, value in UserSettings.Get(group='nviz', key='volume',
                                               subkey=attrb).iteritems():
                data['attribute'][attrb][key] = value
            data['attribute'][attrb]['update'] = None
        
        #
        # draw
        #
        data['draw']['all'] = False # apply only for current surface
        for control, value in UserSettings.Get(group='nviz', key='surface', subkey='draw').iteritems():
            if control[:3] == 'res':
                if not data['draw'].has_key('resolution'):
                    data['draw']['resolution'] = {}
                if not data['draw']['resolution'].has_key('update'):
                    data['draw']['resolution']['update'] = None
                data['draw']['resolution'][control[4:]] = value
                continue
            
            if control == 'wire-color':
                value = str(value[0]) + ':' + str(value[1]) + ':' + str(value[2])
            elif control in ('mode', 'style', 'shading'):
                if not data['draw'].has_key('mode'):
                    data['draw']['mode'] = {}
                continue

            data['draw'][control] = { 'value' : value }
            data['draw'][control]['update'] = None
            
        value, desc = self.GetDrawMode(UserSettings.Get(group='nviz', key='surface', subkey=['draw', 'mode']),
                                       UserSettings.Get(group='nviz', key='surface', subkey=['draw', 'style']),
                                       UserSettings.Get(group='nviz', key='surface', subkey=['draw', 'shading']))

        data['draw']['mode'] = { 'value' : value,
                                 'desc' : desc, 
                                 'update': None }
        
        return data
    
    def SetVolumeDefaultProp(self):
        """Set default volume data properties"""
        data = dict()
        for sec in ('attribute', 'draw', 'position'):
            data[sec] = dict()
            for sec in ('isosurface', 'slice'):
                    data[sec] = list()
        
        #
        # draw
        #
        for control, value in UserSettings.Get(group='nviz', key='volume', subkey='draw').iteritems():
            if control == 'mode':
                continue
            if control == 'shading':
                sel = UserSettings.Get(group='nviz', key='surface', subkey=['draw', 'shading'])
                value, desc = self.GetDrawMode(shade=sel, string=False)

                data['draw']['shading'] = { 'value' : value,
                                            'desc' : desc['shading'] }
            elif control == 'mode':
                sel = UserSettings.Get(group='nviz', key='volume', subkey=['draw', 'mode'])
                if sel == 0:
                    desc = 'isosurface'
                else:
                    desc = 'slice'
                data['draw']['mode'] = { 'value' : sel,
                                         'desc' : desc, }
            else:
                data['draw'][control] = { 'value' : value }

            if not data['draw'][control].has_key('update'):
                data['draw'][control]['update'] = None
        
        #
        # isosurface attributes
        #
        for attrb in ('shine', ):
            data['attribute'][attrb] = {}
            for key, value in UserSettings.Get(group='nviz', key='volume',
                                               subkey=attrb).iteritems():
                data['attribute'][attrb][key] = value
        
        return data
    
    def SetVectorDefaultProp(self):
        """Set default vector data properties"""
        data = dict()
        for sec in ('lines', 'points'):
            data[sec] = {}
        
        self.SetVectorLinesDefaultProp(data['lines'])
        self.SetVectorPointsDefaultProp(data['points'])

        return data
    
    def SetVectorLinesDefaultProp(self, data):
        """Set default vector properties -- lines"""
        # width
        data['width'] = {'value' : UserSettings.Get(group='nviz', key='vector',
                                                    subkey=['lines', 'width']) }
        
        # color
        value = UserSettings.Get(group='nviz', key='vector',
                                 subkey=['lines', 'color'])
        color = str(value[0]) + ':' + str(value[1]) + ':' + str(value[2])
        data['color'] = { 'value' : color }

        # mode
        if UserSettings.Get(group='nviz', key='vector',
                            subkey=['lines', 'flat']):
            type = 'flat'
            map  = None
        else:
            type = 'flat'
            map = None

        data['mode'] = {}
        data['mode']['type'] = type
        data['mode']['update'] = None
        if map:
            data['mode']['surface'] = map

        # height
        data['height'] = { 'value' : UserSettings.Get(group='nviz', key='vector',
                                                      subkey=['lines', 'height']) }

        if data.has_key('object'):
            for attrb in ('color', 'width', 'mode', 'height'):
                data[attrb]['update'] = None
        
    def SetVectorPointsDefaultProp(self, data):
        """Set default vector properties -- points"""
        # size
        data['size'] = { 'value' : UserSettings.Get(group='nviz', key='vector',
                                                    subkey=['points', 'size']) }

        # width
        data['width'] = { 'value' : UserSettings.Get(group='nviz', key='vector',
                                                     subkey=['points', 'width']) }

        # marker
        data['marker'] = { 'value' : UserSettings.Get(group='nviz', key='vector',
                                                      subkey=['points', 'marker']) }

        # color
        value = UserSettings.Get(group='nviz', key='vector',
                                 subkey=['points', 'color'])
        color = str(value[0]) + ':' + str(value[1]) + ':' + str(value[2])
        data['color'] = { 'value' : color }

        # mode
        data['mode'] = { 'type' : 'surface',
                         'surface' : '', }
        
        # height
        data['height'] = { 'value' : UserSettings.Get(group='nviz', key='vector',
                                                      subkey=['points', 'height']) }

        if data.has_key('object'):
            for attrb in ('size', 'width', 'marker',
                          'color', 'surface', 'height'):
                data[attrb]['update'] = None
        
    def GetDrawMode(self, mode=None, style=None, shade=None, string=False):
        """Get surface draw mode (value) from description/selection

        @param mode,style,shade modes
        @param string if True input parameters are strings otherwise
        selections
        """
        if not wxnviz:
            return None
        
        value = 0
        desc = {}

        if string:
            if mode is not None:
                if mode == 'coarse':
                    value |= wxnviz.DM_WIRE
                elif mode == 'fine':
                    value |= wxnviz.DM_POLY
                else: # both
                    value |= wxnviz.DM_WIRE_POLY

            if style is not None:
                if style == 'wire':
                    value |= wxnviz.DM_GRID_WIRE
                else: # surface
                    value |= wxnviz.DM_GRID_SURF
                    
            if shade is not None:
                if shade == 'flat':
                    value |= wxnviz.DM_FLAT
                else: # surface
                    value |= wxnviz.DM_GOURAUD

            return value

        # -> string is False
        if mode is not None:
            if mode == 0: # coarse
                value |= wxnviz.DM_WIRE
                desc['mode'] = 'coarse'
            elif mode == 1: # fine
                value |= wxnviz.DM_POLY
                desc['mode'] = 'fine'
            else: # both
                value |= wxnviz.DM_WIRE_POLY
                desc['mode'] = 'both'

        if style is not None:
            if style == 0: # wire
                value |= wxnviz.DM_GRID_WIRE
                desc['style'] = 'wire'
            else: # surface
                value |= wxnviz.DM_GRID_SURF
                desc['style'] = 'surface'

        if shade is not None:
            if shade == 0:
                value |= wxnviz.DM_FLAT
                desc['shading'] = 'flat'
            else: # surface
                value |= wxnviz.DM_GOURAUD
                desc['shading'] = 'gouraud'
        
        return (value, desc)
    
class WriteWorkspaceFile(object):
    """!Generic class for writing workspace file"""
    def __init__(self, lmgr, file):
        self.file =  file
        self.lmgr = lmgr
        self.indent = 0

        # write header
        self.file.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.file.write('<!DOCTYPE gxw SYSTEM "grass-gxw.dtd">\n')
        self.file.write('%s<gxw>\n' % (' ' * self.indent))
        
        self.indent =+ 4
        
        # layer manager
        windowPos = self.lmgr.GetPosition()
        windowSize = self.lmgr.GetSize()
        file.write('%s<layer_manager dim="%d,%d,%d,%d">\n' % (' ' * self.indent,
                                                              windowPos[0],
                                                              windowPos[1],
                                                              windowSize[0],
                                                              windowSize[1]
                                                              ))
        
        file.write('%s</layer_manager>\n' % (' ' * self.indent))
        
        # list of displays
        for page in range(0, self.lmgr.gm_cb.GetPageCount()):
            mapTree = self.lmgr.gm_cb.GetPage(page).maptree
            region = mapTree.Map.region
            
            displayPos = mapTree.mapdisplay.GetPosition()
            displaySize = mapTree.mapdisplay.GetSize()
            
            file.write('%s<display render="%d" '
                       'mode="%d" showCompExtent="%d" '
                       'constrainRes="%d" '
                       'dim="%d,%d,%d,%d" '
                       'extent="%f,%f,%f,%f">\n' % (' ' * self.indent,
                                                    int(mapTree.mapdisplay.autoRender.IsChecked()),
                                                    mapTree.mapdisplay.toggleStatus.GetSelection(),
                                                    int(mapTree.mapdisplay.showRegion.IsChecked()),
                                                    int(mapTree.mapdisplay.compResolution.IsChecked()),
                                                    displayPos[0],
                                                    displayPos[1],
                                                    displaySize[0],
                                                    displaySize[1],
                                                    region['w'],
                                                    region['s'],
                                                    region['e'],
                                                    region['n']
                                                    ))
            
            # list of layers
            item = mapTree.GetFirstChild(mapTree.root)[0]
            self.__writeLayer(mapTree, item)
            file.write('%s</display>\n' % (' ' * self.indent))

        self.indent =- 4
        file.write('%s</gxw>\n' % (' ' * self.indent))

    def __filterValue(self, value):
        """!Make value XML-valid"""
        value = value.replace('<', '&lt;')
        value = value.replace('>', '&gt;')
        
        return value
    
    def __writeLayer(self, mapTree, item):
        """!Write bunch of layers to GRASS Workspace XML file"""
        self.indent += 4
        itemSelected = mapTree.GetSelections()
        while item and item.IsOk():
            type = mapTree.GetPyData(item)[0]['type']
            if type != 'group':
                maplayer = mapTree.GetPyData(item)[0]['maplayer']
            else:
                maplayer = None

            checked = int(item.IsChecked())
            if type == 'command':
                cmd = mapTree.GetPyData(item)[0]['maplayer'].GetCmd(string=True)
                self.file.write('%s<layer type="%s" name="%s" checked="%d">\n' % \
                               (' ' * self.indent, type, cmd, checked));
                self.file.write('%s</layer>\n' % (' ' * self.indent));
            elif type == 'group':
                name = mapTree.GetItemText(item)
                self.file.write('%s<group name="%s" checked="%d">\n' % \
                               (' ' * self.indent, name, checked));
                self.indent += 4
                subItem = mapTree.GetFirstChild(item)[0]
                self.__writeLayer(mapTree, subItem)
                self.indent -= 4
                self.file.write('%s</group>\n' % (' ' * self.indent));
            else:
                cmd = mapTree.GetPyData(item)[0]['maplayer'].GetCmd(string=False)
                name = mapTree.GetItemText(item)
                # remove 'opacity' part
                if '(opacity' in name:
                    name = name.split('(', -1)[0].strip()
                opacity = maplayer.GetOpacity(float=True)
                self.file.write('%s<layer type="%s" name="%s" checked="%d" opacity="%f">\n' % \
                               (' ' * self.indent, type, name, checked, opacity));

                self.indent += 4
                # selected ?
                if item in itemSelected:
                    self.file.write('%s<selected />\n' % (' ' * self.indent))
                # layer properties
                self.file.write('%s<task name="%s">\n' % (' ' * self.indent, cmd[0]))
                self.indent += 4
                for key, val in cmd[1].iteritems():
                    if key == 'flags':
                        for f in val:
                            self.file.write('%s<flag name="%s" />\n' %
                                            (' ' * self.indent, f))
                    else: # parameter
                        self.file.write('%s<parameter name="%s">\n' %
                                   (' ' * self.indent, key))
                        self.indent += 4
                        self.file.write('%s<value>%s</value>\n' %
                                   (' ' * self.indent, self.__filterValue(val)))
                        self.indent -= 4
                        self.file.write('%s</parameter>\n' % (' ' * self.indent));
                self.indent -= 4
                self.file.write('%s</task>\n' % (' ' * self.indent));
                nviz = mapTree.GetPyData(item)[0]['nviz']
                if nviz:
                    self.file.write('%s<nviz>\n' % (' ' * self.indent));
                    if maplayer.type == 'raster':
                        self.__writeNvizSurface(nviz['surface'])
                    elif maplayer.type == 'vector':
                        self.__writeNvizVector(nviz['vector'])
                    self.file.write('%s</nviz>\n' % (' ' * self.indent));
                self.indent -= 4
                self.file.write('%s</layer>\n' % (' ' * self.indent));
            item = mapTree.GetNextSibling(item)
        self.indent -= 4

    def __writeNvizSurface(self, data):
        """!Save Nviz raster layer properties to workspace

        @param data Nviz layer properties
        """
        if not data.has_key('object'): # skip disabled
            return

        self.indent += 4
        self.file.write('%s<surface>\n' % (' ' * self.indent))
        self.indent += 4
        for attrb in data.iterkeys():
            if len(data[attrb]) < 1: # skip empty attributes
                continue
            if attrb == 'object':
                continue
            
            for name in data[attrb].iterkeys():
                # surface attribute
                if attrb == 'attribute':
                    self.file.write('%s<%s name="%s" map="%d">\n' % \
                                   (' ' * self.indent, attrb, name, data[attrb][name]['map']))
                    self.indent += 4
                    self.file.write('%s<value>%s</value>\n' % (' ' * self.indent, data[attrb][name]['value']))
                    self.indent -= 4
                    # end tag
                    self.file.write('%s</%s>\n' % (' ' * self.indent, attrb))

            # draw mode
            if attrb == 'draw':
                self.file.write('%s<%s' %(' ' * self.indent, attrb))
                if data[attrb].has_key('mode'):
                    for tag, value in data[attrb]['mode']['desc'].iteritems():
                        self.file.write(' %s="%s"' % (tag, value))
                self.file.write('>\n') # <draw ...>

                if data[attrb].has_key('resolution'):
                    self.indent += 4
                    for type in ('coarse', 'fine'):
                        self.file.write('%s<resolution type="%s">\n' % (' ' * self.indent, type))
                        self.indent += 4
                        self.file.write('%s<value>%d</value>\n' % (' ' * self.indent,
                                                                   data[attrb]['resolution'][type]))
                        self.indent -= 4
                        self.file.write('%s</resolution>\n' % (' ' * self.indent))

                if data[attrb].has_key('wire-color'):
                    self.file.write('%s<wire_color>\n' % (' ' * self.indent))
                    self.indent += 4
                    self.file.write('%s<value>%s</value>\n' % (' ' * self.indent,
                                                               data[attrb]['wire-color']['value']))
                    self.indent -= 4
                    self.file.write('%s</wire_color>\n' % (' ' * self.indent))
                self.indent -= 4
            
            # position
            elif attrb == 'position':
                self.file.write('%s<%s>\n' %(' ' * self.indent, attrb))
                i = 0
                for tag in ('x', 'y', 'z'):
                    self.indent += 4
                    self.file.write('%s<%s>%d</%s>\n' % (' ' * self.indent, tag,
                                                        data[attrb][tag], tag))
                    i += 1
                    self.indent -= 4

            if attrb != 'attribute':
                # end tag
                self.file.write('%s</%s>\n' % (' ' * self.indent, attrb))

        self.indent -= 4
        self.file.write('%s</surface>\n' % (' ' * self.indent))
        self.indent -= 4

    def __writeNvizVector(self, data):
        """!Save Nviz vector layer properties (lines/points) to workspace

        @param data Nviz layer properties
        """
        self.indent += 4
        for attrb in data.iterkeys():
            if len(data[attrb]) < 1: # skip empty attributes
                continue

            if not data[attrb].has_key('object'): # skip disabled
                continue
            if attrb == 'lines':
                self.file.write('%s<v%s>\n' % (' ' * self.indent, attrb))
            elif attrb == 'points':
                markerId = data[attrb]['marker']
                marker = UserSettings.Get(group='nviz', key='vector',
                                          subkey=['points', 'marker'], internal=True)[markerId]
                self.file.write('%s<v%s marker="%s">\n' % (' ' * self.indent,
                                                           attrb,
                                                           marker))
            self.indent += 4
            for name in data[attrb].iterkeys():
                if name in ('object', 'marker'):
                    continue
                if name == 'mode':
                    self.file.write('%s<%s type="%s">\n' % (' ' * self.indent, name,
                                                          data[attrb][name]['type']))
                    if data[attrb][name]['type'] == 'surface':
                        self.indent += 4
                        self.file.write('%s<map>%s</map>\n' % (' ' * self.indent,
                                                               data[attrb][name]['surface']))
                        self.indent -= 4
                    self.file.write('%s</%s>\n' % ((' ' * self.indent, name)))
                else:
                    self.file.write('%s<%s>\n' % (' ' * self.indent, name))
                    self.indent += 4
                    self.file.write('%s<value>%s</value>\n' % (' ' * self.indent, data[attrb][name]['value']))
                    self.indent -= 4
                    self.file.write('%s</%s>\n' % (' ' * self.indent, name))
            self.indent -= 4
            self.file.write('%s</v%s>\n' % (' ' * self.indent, attrb))

        self.indent -= 4

class ProcessGrcFile(object):
    def __init__(self, filename):
        """!Process GRC file"""
        self.filename = filename

        # elements
        self.inGroup = False
        self.inRaster = False
        self.inVector = False

        # list of layers
        self.layers = []

        # error message
        self.error = ''
        self.num_error = 0

    def read(self, parent):
        """!Read GRC file

        @param parent parent window

        @return list of map layers
        """
        try:
            file = open(self.filename, "r")
        except IOError:
            wx.MessageBox(parent=parent,
                          message=_("Unable to open file <%s> for reading.") % self.filename,
                          caption=_("Error"), style=wx.OK | wx.ICON_ERROR)
            return []

        line_id = 1
        for line in file.readlines():
            self.process_line(line.rstrip('\n'), line_id)
            line_id +=1

        file.close()

        if self.num_error > 0:
            wx.MessageBox(parent=parent,
                          message=_("Some lines were skipped when reading settings "
                                    "from file <%(file)s>.\nSee 'Command output' window for details.\n\n"
                                    "Number of skipped lines: %(line)d") % \
                                        { 'file' : self.filename, 'line' : self.num_error },
                          caption=_("Warning"), style=wx.OK | wx.ICON_EXCLAMATION)
            parent.goutput.WriteLog('Map layers loaded from GRC file <%s>' % self.filename)
            parent.goutput.WriteLog('Skipped lines:\n%s' % self.error)

        return self.layers

    def process_line(self, line, line_id):
        """!Process line definition"""
        element = self._get_element(line)
        if element == 'Group':
            self.groupName = self._get_value(line)
            self.layers.append({
                    "type"    : 'group',
                    "name"    : self.groupName,
                    "checked" : None,
                    "opacity" : None,
                    "cmd"     : None,
                    "group"   : self.inGroup,
                    "display" : 0 })
            self.inGroup = True

        elif element == '_check':
            if int(self._get_value(line)) ==  1:
                self.layers[-1]['checked'] = True
            else:
                self.layers[-1]['checked'] = False
            
        elif element == 'End':
            if self.inRaster:
                self.inRaster = False
            elif self.inVector:
                self.inVector = False
            elif self.inGroup:
                self.inGroup = False
            elif self.inGridline:
                self.inGridline = False
        
        elif element == 'opacity':
            self.layers[-1]['opacity'] = float(self._get_value(line))

        # raster
        elif element == 'Raster':
            self.inRaster = True
            self.layers.append({
                    "type"    : 'raster',
                    "name"    : self._get_value(line),
                    "checked" : None,
                    "opacity" : None,
                    "cmd"     : ['d.rast'],
                    "group"   : self.inGroup,
                    "display" : 0})

        elif element == 'map' and self.inRaster:
            self.layers[-1]['cmd'].append('map=%s' % self._get_value(line))
            
        elif element == 'overlay' and self.inRaster:
            if int(self._get_value(line)) == 1:
                self.layers[-1]['cmd'].append('-o')
            
        elif element == 'rastquery' and self.inRaster:
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('catlist=%s' % value)
            
        elif element == 'bkcolor' and self.inRaster:
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('bg=%s' % value)

        # vector
        elif element == 'Vector':
            self.inVector = True
            self.layers.append({
                    "type"    : 'vector',
                    "name"    : self._get_value(line),
                    "checked" : None,
                    "opacity" : None,
                    "cmd"     : ['d.vect'],
                    "group"   : self.inGroup,
                    "display" : 0})

        elif element == 'vect' and self.inVector:
            self.layers[-1]['cmd'].append('map=%s' % self._get_value(line))
                
        elif element in ('display_shape',
                         'display_cat',
                         'display_topo',
                         'display_dir',
                         'display_attr',
                         'type_point',
                         'type_line',
                         'type_boundary',
                         'type_centroid',
                         'type_area',
                         'type_face') and self.inVector:
            
            if int(self._get_value(line)) == 1:
                name = element.split('_')[0]
                type = element.split('_')[1]
                paramId = self._get_cmd_param_index(self.layers[-1]['cmd'], name)
                if paramId == -1:
                    self.layers[-1]['cmd'].append('%s=%s' % (name, type))
                else:
                    self.layers[-1]['cmd'][paramId] += ',%s' % type

        elif element in ('color',
                         'fcolor',
                         'lcolor') and self.inVector:
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('%s=%s' % (element,
                                                         self._color_name_to_rgb(value)))

        elif element == 'rdmcolor' and self.inVector:
            if int(self._get_value(line)) == 1:
                self.layers[-1]['cmd'].append('-c')

        elif element == 'sqlcolor' and self.inVector:
            if int(self._get_value(line)) == 1:
                self.layers[-1]['cmd'].append('-a')

        elif element in ('icon',
                         'size',
                         'layer',
                         'xref',
                         'yref',
                         'lsize',
                         'where',
                         'minreg',
                         'maxreg') and self.inVector:
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('%s=%s' % (element,
                                                         value))
        
        elif element == 'lwidth':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('width=%s' % value)

        elif element == 'lfield':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('llayer=%s' % value)
                                        
        elif element == 'attribute':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('attrcol=%s' % value)

        elif element == 'cat':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('cats=%s' % value)

        # gridline
        elif element == 'gridline':
            self.inGridline = True
            self.layers.append({
                    "type"    : 'grid',
                    "name"    : self._get_value(line),
                    "checked" : None,
                    "opacity" : None,
                    "cmd"     : ['d.grid'],
                    "group"   : self.inGroup,
                    "display" : 0})

        elif element == 'gridcolor':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('color=%s' % self._color_name_to_rgb(value))

        elif element == 'gridborder':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('bordercolor=%s' % self._color_name_to_rgb(value))

        elif element == 'textcolor':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('textcolor=%s' % self._color_name_to_rgb(value))

        elif element in ('gridsize',
                         'gridorigin'):
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('%s=%s' % (element[4:], value))

        elif element in 'fontsize':
            value = self._get_value(line)
            if value != '':
                self.layers[-1]['cmd'].append('%s=%s' % (element, value))
        
        elif element == 'griddraw':
            value = self._get_value(line)
            if value == '0':
                self.layers[-1]['cmd'].append('-n')
                
        elif element == 'gridgeo':
            value = self._get_value(line)
            if value == '1':
                self.layers[-1]['cmd'].append('-g')
        
        elif element == 'borderdraw':
            value = self._get_value(line)
            if value == '0':
                self.layers[-1]['cmd'].append('-b')

        elif element == 'textdraw':
            value = self._get_value(line)
            if value == '0':
                self.layers[-1]['cmd'].append('-t')
        
        else:
            self.error += _(' row %d:') % line_id + line + os.linesep
            self.num_error += 1

    def _get_value(self, line):
        """!Get value of element"""
        try:
            return line.strip(' ').split(' ')[1].strip(' ')
        except:
            return ''

    def _get_element(self, line):
        """!Get element tag"""
        return line.strip(' ').split(' ')[0].strip(' ')

    def _get_cmd_param_index(self, cmd, name):
        """!Get index of parameter in cmd list

        @param cmd cmd list
        @param name parameter name

        @return index
        @return -1 if not found
        """
        i = 0
        for param in cmd:
            if '=' not in param:
                i += 1
                continue
            if param.split('=')[0] == name:
                return i

            i += 1

        return -1

    def _color_name_to_rgb(self, value):
        """!Convert color name (#) to rgb values"""
        col = wx.NamedColour(value)
        return str(col.Red()) + ':' + \
            str(col.Green()) + ':' + \
            str(col.Blue())
