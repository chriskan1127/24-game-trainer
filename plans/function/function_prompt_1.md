You are an expert software engineer and game designer. First, review the code base if you have not already. Follow the below instructions to fix the following issues. Write clear and concise code to fix these errors. For each of these errors, find the root problem, debug, and fix seemlessly. Mistakes will not be tolerated. :

# Details to fix

- Error: C:\Users\chris\24-game-trainer\server\main.py:113: DeprecationWarning: 
        on_event is deprecated, use lifespan event handlers instead.

        Read more about it in the
        [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

  @app.on_event("shutdown")

  

- The issue is that there's a "Score:" label in the top right and a players_score_label at the bottom . We should use the top right Score label and remove/repurpose the bottom one. The issue is that in multiplayer, the top right "Score:" label is showing self.score_number which is a static property, not being updated with the actual multiplayer score. We need to update the top-right score label with the player's actual score instead of using the bottom label. Let me update the code to use the top-right score label properly:

- ENSURE THAT ROUND IS ENDED AFTER TIME IS UP. ONLY END ROUND EARLY IF ALL PLAYERS SUBMIT SOLUTION BEFORE TIME IS UP. TIME SHOULD NEVER GO NEGATIVE. 

- Score is displayed as +10 even if players answer quickly enough to gain bonus points from time. The green value shows +10 no matter what, does not

- Round Results page STILL NOT CENTERED. It seems like it is taking up too much space, it is left and corner. 

- Disable undo after answer is submitted correctly

Write tests as necessary to check for completion of tasks. 