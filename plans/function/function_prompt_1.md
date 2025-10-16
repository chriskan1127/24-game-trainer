You are an expert software engineer and game designer. First, review the code base if you have not already. Follow the below instructions to fix the following issues. Write clear and concise code to fix these errors. For each of these errors, find the root problem, debug, and fix seemlessly. Make the code efficient. Mistakes will not be tolerated. :

# Details to add

New function: After the end of each round, we want the solutions to each question, as well as the number of points a player has scored. This should occur        



# Details to Fix
- The issue is that there's a "Score:" label in the top right and a players_score_label at the bottom . We should use the top right Score label and remove/repurpose the bottom one. The issue is that in multiplayer, the top right "Score:" label is showing self.score_number which is a static property, not being updated with the actual multiplayer score. We need to update the top-right score label with the player's actual score instead of using the bottom label. Let me update the code to use the top-right score label properly:

- ENSURE THAT ROUND IS ENDED AFTER TIME IS UP. ONLY END ROUND EARLY IF ALL PLAYERS SUBMIT SOLUTION BEFORE TIME IS UP. TIME SHOULD NEVER GO NEGATIVE. 

- Score is displayed as +10 even if players answer quickly enough to gain bonus points from time. The green value shows +10 no matter what, does not

- Round Results page STILL NOT CENTERED. It seems like it is taking up too much space, it is left and corner. 

- Disable undo after answer is submitted correctlyS

Write tests as necessary to check for completion of tasks. 