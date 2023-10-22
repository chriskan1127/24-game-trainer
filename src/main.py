from kivy.app import App
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.properties import *
from kivy.uix.button import Button
from kivy.vector import Vector
from kivy.clock import Clock
from kivy.animation import Animation
from random import randint 
from copy import copy
from kivy.uix.floatlayout import FloatLayout

class Solve24Game(Widget):
    remaining_nums = BoundedNumericProperty(4, min=0, max=4, errorvalue=4)
    time_passed = BoundedNumericProperty(0, min=0, max=30, errorvalue=30)
    ops = ListProperty([])
    ops_state = OptionProperty("None", options=["Undo", "+", "-", "x", "/", "None"])
    previous_numberpanel = ObjectProperty(None)
    operationpanel = ObjectProperty(None)
    timelabel = ObjectProperty(None)
    scorelabel = ObjectProperty(None)
    targetlabel = ObjectProperty(None)
    
    def timer_tick(self, dt=None):
        self.time_passed = self.time_passed + 1
        self.timelabel.time_remaining = self.timelabel.time_remaining - 1

    def start_state(self):
        self.main_numberpanel = ObjectProperty(None)
        self.remaining_nums = 4
        new_numberpanel = NumberPanel(pos_hint = {'x': 0.18, 'y': 0.3})
        self.ids.floatlayout.add_widget(new_numberpanel)
        self.time_passed = 0
        self.timelabel.time_remaining = self.time_duration
        self.main_numberpanel = new_numberpanel
        self.previous_numberpanel = self.main_numberpanel
        self.main_numberpanel.start()
        self.bind(remaining_nums=self.finishedgame_callback)
        self.bind(time_passed=self.out_of_time)
        self.ops_state = "None"
        if len(self.ops) > 0:
            self.ops.pop()
        self.operationpanel.operation_id = 'None'
    
    def out_of_time(self, instance, value):
        if value == self.time_duration:
            #self.ops.pop()
            self.scorelabel.score_number = 0
            self.ids.floatlayout.remove_widget(self.main_numberpanel)
            self.start_state()

    def clear_operations(self):
        self.operationpanel.ids[self.operationpanel.operation_id].remove_operation()
    
    def finishedgame_callback(self, instance, value):
        if value == 1:
            if self.main_numberpanel.ids[self.main_numberpanel.first_operation].int_value == self.targetlabel.target_number:
                #self.ops.pop()
                self.scorelabel.score_number = self.scorelabel.score_number + 1
                self.ids.floatlayout.remove_widget(self.main_numberpanel)
                self.start_state()

class OperationPanel(Widget):
    operation_id = OptionProperty("None", options=["undo", "add", "subtract", "multiply", "divide", "None"])
    undo = ObjectProperty(None)
    add = ObjectProperty(None)
    subtract = ObjectProperty(None)
    divide = ObjectProperty(None)
    multiply = ObjectProperty(None)

    def add_op(self, block_instance):
        for block_id, block in self.ids.items():
            if block == block_instance:
                self.operation_id = block_id
                break

class OperationBlock(Button, Widget):
    activated = BooleanProperty(0)
    
    def remove_operation(self): #removes operation from state 
        self.background_color = (1, 0, 0, 1)
        self.parent.parent.parent.parent.ops_state = 'None'
        self.parent.parent.operation_id = 'None'
        self.activated = False
    
    def add_operation(self): #adds operation to state
        self.parent.parent.parent.parent.ops_state = self.text
        self.parent.parent.add_op(self) #adds block's id as operation id (operation to be executed)
        self.activated = True
    
    def on_press(self):
        self.background_color = (0, 1, 0.4, 1)
    
    def on_release(self):
        if self.activated is True:
            self.remove_operation()
        else:
            if len(self.parent.parent.parent.parent.ops) < 1:
                self.background_color = (1, 0, 0, 1)
            else:
                if self.parent.parent.operation_id is not 'None':
                    self.parent.parent.ids[self.parent.parent.operation_id].remove_operation()
                self.add_operation()

class UndoBlock(Button, Widget):
    def on_press(self):
        self.background_color = (0, 1, 0.4, 1)
    
    def on_release(self):
        self.background_color = (1, 0, 0, 1)
        if self.parent.parent.parent.parent.ops_state is not 'None':
            self.parent.parent.parent.parent.clear_operations()
        self.parent.parent.parent.parent.ids.floatlayout.remove_widget(self.parent.parent.parent.parent.main_numberpanel)
        self.parent.parent.parent.parent.main_numberpanel = self.parent.parent.parent.parent.previous_numberpanel
        self.parent.parent.parent.parent.ids.floatlayout.add_widget(self.parent.parent.parent.parent.main_numberpanel)

#used for binding
def numberpanel_callback(instance, value):
        if value == 1:
            if instance.ids[instance.first_operation].int_value == instance.parent.parent.targetlabel.target_number:
                instance.parent.parent.scorelabel.score_number = instance.parent.parent.scorelabel.score_number + 1
                instance.parent.parent.start_state()

class NumberPanel(Widget):
    number1 = ObjectProperty(None)
    number2 = ObjectProperty(None)
    number3 = ObjectProperty(None)
    number4 = ObjectProperty(None)
    
    first_operation = OptionProperty("None", options=["number1", "number2", "number3", "number4", "None"])
    
    def add_first_op(self, block_instance):
        for block_id, block in self.ids.items():
            if block == block_instance:
                self.first_operation = block_id
                break

    def start(self):
        self.number1.generate_value()
        self.number2.generate_value()
        self.number3.generate_value()
        self.number4.generate_value()
        self.remaining_nums = 4
    
    def compute(self, block_instance):
        self.parent.parent.previous_numberpanel = self.parent.parent.main_numberpanel
        block_id = self.first_operation
        int1 = self.ids[block_id].int_value
        int2 = block_instance.int_value
        operation = self.parent.parent.ops_state
        output = 0
        if operation is '+':
            output = int1 + int2
        elif operation is '-':
            output = int1 - int2
        elif operation is 'x':
            output = int1 * int2
        elif operation is '/':
            output = int1 / int2
        anim1 = Animation(x=block_instance.x, y=block_instance.y, duration=0.6)
        anim1.start(self.ids[block_id])
        self.ids.floatlayout.remove_widget(self.ids[block_id])
        anim2 = Animation(size_hint_value = 0.49, duration=0.10) + Animation(size_hint_value = 0.45, duration=0.09)
        anim2.start(block_instance)
        block_instance.adjust_value(output) #change block's number
        block_instance.remove_operation()
        block_instance.background_color = (0, 1, 0.4, 1)
        block_instance.add_operation()
        self.parent.parent.clear_operations()
        self.parent.parent.remaining_nums = self.parent.parent.remaining_nums - 1
        

class NumberBlock(Button, Widget):
    int_value = NumericProperty(0)
    activated = BooleanProperty(0)
    
    def remove_operation(self): #removes operation from state 
        self.background_color = (1, 0, 0, 1)
        self.parent.parent.parent.parent.ops.pop()
        self.parent.parent.first_operation = "None"
        self.activated = False

    def add_operation(self):
        self.parent.parent.parent.parent.ops.append(self.int_value)
        self.parent.parent.add_first_op(self)
        self.activated = True
    
    def generate_value(self):
        value = randint(1, 13)
        self.text = str(value)
        self.int_value = value

    def adjust_value(self, int):
        self.int_value = int
        self.text = str(int)
    
    def on_press(self):
        self.background_color = (0, 1, 0.4, 1)
        self.size_hint_value = 0.41
   
    def on_release(self):
        self.size_hint_value = 0.45
        if self.activated is True:
            self.remove_operation()
        else:
            if len(self.parent.parent.parent.parent.ops) < 1:
                self.add_operation()
            elif self.parent.parent.parent.parent.ops_state == 'None':
                self.parent.parent.ids[self.parent.parent.first_operation].remove_operation()
                self.add_operation()
            else:
                self.parent.parent.compute(self)

class Solve24App(App):
    def build(self):
        game = Solve24Game()
        game.start_state()
        Clock.schedule_interval(game.timer_tick, 1)
        return game
    
if __name__ == '__main__':
    Solve24App().run()
