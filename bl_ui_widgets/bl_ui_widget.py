import bpy
import gpu
from gpu_extras.batch import batch_for_shader


class BL_UI_Widget:

    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y
        self.width = width
        self.height = height
        self._bg_color = (0.8, 0.8, 0.8, 1.0)
        self._tag = None
        self.context = None
        self.__inrect = False
        self._mouse_down = False
        self._mouse_down_right = False
        self._is_visible = True
        self._is_active = True #if the widget needs to be disabled

    def set_location(self, x, y):
        # if self.x != x or self.y != y or self.x_screen != x or self.y_screen != y:
        #     bpy.context.region.tag_redraw()
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y
        self.update(x,y)


    @property
    def bg_color(self):
        return self._bg_color

    @bg_color.setter
    def bg_color(self, value):
        if value != self._bg_color:
            bpy.context.region.tag_redraw()
        self._bg_color = value

    @property
    def visible(self):
        return self._is_visible

    @visible.setter
    def visible(self, value):
        if value != self._is_visible:
            bpy.context.region.tag_redraw()
        self._is_visible = value

    @property
    def active(self):
        return self._is_active

    @visible.setter
    def active(self, value):
        if value != self._is_active:
            bpy.context.region.tag_redraw()
        self._is_active = value

    @property
    def tag(self):
        return self._tag

    @tag.setter
    def tag(self, value):
        self._tag = value

    def draw(self):
        if not self._is_visible:
            return

        self.shader.bind()
        self.shader.uniform_float("color", self._bg_color)

        self.batch_panel.draw(self.shader)

    def init(self, context):
        self.context = context
        self.update(self.x, self.y)

    def update(self, x, y):

        area_height = self.get_area_height()
        self.x_screen = x
        self.y_screen = y

        indices = ((0, 1, 2), (0, 2, 3))

        y_screen_flip = area_height - self.y_screen

        # bottom left, top left, top right, bottom right
        vertices = (
                    (self.x_screen, y_screen_flip),
                    (self.x_screen, y_screen_flip - self.height),
                    (self.x_screen + self.width, y_screen_flip - self.height),
                    (self.x_screen + self.width, y_screen_flip))

        self.shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        self.batch_panel = batch_for_shader(self.shader, 'TRIS', {"pos" : vertices}, indices=indices)
        bpy.context.region.tag_redraw()

    def handle_event(self, event):
        '''
        returns True if the event was handled by the widget
        # 'handled_pass', if the event was handled but the event should be passed to other widgets
        False if the event was not handled by the widget
        '''

        if not self._is_visible:
            return False
        if not self._is_active:
            return False

        x = event.mouse_region_x
        y = event.mouse_region_y

        if (event.type == 'LEFTMOUSE'):
            if (event.value == 'PRESS'):
                self._mouse_down = True
                bpy.context.region.tag_redraw()
                return self.mouse_down(x, y)
            else:
                self._mouse_down = False
                bpy.context.region.tag_redraw()
                self.mouse_up(x, y)
                return False

        elif (event.type == 'RIGHTMOUSE'):

            if (event.value == 'PRESS'):
                self._mouse_down_right = True
                bpy.context.region.tag_redraw()
                return self.mouse_down_right(x, y)
            else:
                self._mouse_down_right = False
                bpy.context.region.tag_redraw()
                self.mouse_up(x, y)

        elif (event.type == 'MOUSEMOVE'):
            self.mouse_move(x, y)
            inrect = self.is_in_rect(x, y)

            # we enter the rect
            if not self.__inrect and inrect:
                self.__inrect = True
                self.mouse_enter(event, x, y)
                # we tag redraw since the hover colors are picked in the draw function
                bpy.context.region.tag_redraw()

            # we are leaving the rect
            elif self.__inrect and not inrect:
                self.__inrect = False
                self.mouse_exit(event, x, y)
                bpy.context.region.tag_redraw()

            #return always false to enable mouse exit events on other buttons.(would sometimes not hide the tooltip)
            return False # self.__inrect

        elif event.value == 'PRESS' and self.__inrect and (event.ascii != '' or event.type in self.get_input_keys()):

            return self.text_input(event)

        return False

    def get_input_keys(self)                :
        return []

    def get_area_height(self):
        return self.context.area.height

    def is_in_rect(self, x, y):
        area_height = self.get_area_height()

        widget_y = area_height - self.y_screen
        if (
            (self.x_screen <= x <= (self.x_screen + self.width)) and
            (widget_y >= y >= (widget_y - self.height))
            ):
            # print('is in rect!?')
            # print('area height', area_height)
            # print ('x sceen ',self.x_screen,'x ', x, 'width', self.width)
            # print ('widghet y', widget_y,'y', y, 'height',self.height)
            return True

        return False

    def text_input(self, event):
        return False

    def mouse_down(self, x, y):
        return self.is_in_rect(x,y)

    def mouse_down_right(self, x, y):
        return self.is_in_rect(x,y)

    def mouse_up(self, x, y):
        pass

    def mouse_enter_func(self, widget):
        pass

    def set_mouse_enter(self, mouse_enter_func):
        self.mouse_enter_func = mouse_enter_func

    def call_mouse_enter(self):
        try:
            if self.mouse_enter_func:
                self.mouse_enter_func(self)
        except Exception as e:
            print(e)

    def mouse_enter(self, event, x, y):
        self.call_mouse_enter()

    def set_mouse_exit(self, mouse_exit_func):
        self.mouse_exit_func = mouse_exit_func

    def call_mouse_exit(self):
        try:
            if self.mouse_exit_func:
                self.mouse_exit_func(self)
        except:
            pass

    def mouse_exit(self, event, x, y):
        self.call_mouse_exit()

    def mouse_move(self, x, y):
        pass
