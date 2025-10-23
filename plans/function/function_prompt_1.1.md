You are an expert software engineer and game designer. First, review the code base if you have not already. Follow the below instructions to fix the following issues. Write clear and concise code to fix these errors. For each of these errors, find the root problem, debug, and fix seemlessly. Make the code efficient. Mistakes will not be tolerated. 

# Details to Fix:

- When the round ends, and we go to round results screen, before the next round starts, we should unfreeze all controls again. Thus, all buttons should be usable prior to next round starting (for example, while we are on round results screen)

- Leaderboard should populate starting end of Round 1, even if nobody scores any points.

- Currently, Round Results page is not properly displaying the scores. When a players get a question right, the score is properly updated and logged in the servers, but is not being shown in the RoundResultsScreen. Make sure this screen is pulling the proper data from the server.

Write tests as necessary to check for completion of tasks. 