You are an expert software engineer and game designer. First, review the code base if you have not already. Follow the below instructions to fix the following issues. Write clear and concise code to fix these errors. For each of these errors, find the root problem, debug, and fix seemlessly. Make the code efficient. Mistakes will not be tolerated. 

# Details to Fix
- Players: still at bottom of the screen of the game when round 1 begins. Remove this from the game display without simply changing its color or opacity.  

- The issue is that there's a "Score:" label in the top right and a players_score_label at the bottom. We should use the top right Score label and remove the bottom one. The issue is that in multiplayer, the top right "Score:" label is showing self.score_number which is a static property, not being updated with the actual multiplayer score. We need to update the top-right score label with the player's actual score instead of using the bottom label. 

- The score is not being updated, even after players succesfully answer questions. It seems like points are being properly allocated and stored, just not displayed on the frontend. 

- Score is displayed as +10 even if players answer quickly enough to gain bonus points from time. The green value shows +10 no matter what, we want it to show what they actually scored. This is known from the system: submission_processor displays "submission_processor:Accepted submission from player 31188336-b2a4-493d-b989-563b3f164fdc in room UNN4: 15 points (10 base + 5 speed bonus)".

- Round Results page STILL NOT CENTERED. It seems like it is taking up too much space, it is left and in the corner. Try all avenues to fix this issue. Remember you are an expert at Kivy, try all solutions that will yield a centered page. 

- Disable undo after answer is submitted correctly.

- When choosing a solution, we want to choose the first solution that does not contain a fraction AND does not contain a negative number. If there is no solution that has neither negative number nor fraction, then choose last solution. This can be edited in problem_pool_service.py. 

- Major debug: If a player is in the middle of a choosing a solution when their time runs out, their game ends. For example, when clicking on a button and the timer runs out, the following error is displayed: 
 File "C:\Users\chris\miniconda3\envs\24-game\Lib\site-packages\kivy\uix\behaviors\button.py", line 179, in on_touch_up
     self.dispatch('on_release')
     ~~~~~~~~~~~~~^^^^^^^^^^^^^^
   File "kivy\\_event.pyx", line 731, in kivy._event.EventDispatcher.dispatch
   File "C:\Users\chris\24-game-trainer\src\multiplayer_main.py", line 1499, in on_release
     if len(self.parent.parent.parent.parent.ops) < 1:
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 AttributeError: 'NoneType' object has no attribute 'parent'
 This needs to be prevented. Think about ways to solve this issue that do not involve hard coding, but instead systematically solve this issue. This solution could be related to the solution of freezing all buttons when a player succesfully submits answer. One thought is to immediately just freeze all buttons (set them to false) or unselect everything as soon as time runs out. Choose a robust and consistent solution to this issue so that no matter what the user is clicking or holding down at the time of the round ending, they are not disconnected / no errors occur. 

Write tests as necessary to check for completion of tasks. 