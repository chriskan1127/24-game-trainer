You are an expert game designer that ensures an aesthetic design and smooth game playing experience. You have an expertise in python and Kivy. While reading this prompt, consider that we want this game to be played by all backgrounds and should thus appeal to a large crowd. Also note that we want to ensure that all functionality is maintained. These changes are purely for making the game more visually appealing. Lastly, make as many of these edits happen in the .kv file as possible for efficiency. Concisely but thoroughly make the following changes:

# Home Screens:

- In all instances of displaying the user in their screen, we do not need (you) prefacing the user. Instead, the user's name should simply be consistently bolded. Ensure this is done properly at all instances. Check thoroughly.
- Instead of having the text box to enter game code in the home screen, we should just have a join game or create game tab in the home screen, along with tab to enter name. In other words, remove the Game Code textbox in this screen. Then, when users click to join a game, they can enter game code in a separate page that just has a textbox to enter game code. This should make it more clear on how to join a game or start a game. 
- Make all textboxes taller so that when a user enters their name it can be fully seen within the textbox and the font inside of each textbox more aesthetic and clearer. Instead of saying "Enter Your Name", just have it say "Name". Instead of "Enter game code to join", display "Game Code". 

# RoundResultsScreen aesthetics:
- Background in the RoundResultsScreen should be an aesthetic white appearance, with text that suits the aesthetic of the game itself. 
- Top-left of screen should indicate how many points you earned that round. Below that should contain the solution to the problem. These should be partitioned on the left half of the screen. On the right half of the screen should be leaderboards. 
- Improve leaderboard aesthetics, without adding emojis. There should be a square box (with rounded corners) surrounding the leaderboards. Make it minimalistic and clean, in similar fashion with the rest of the game. At the top of the leaderboard should say "Leaderboard". 
 
Before we continue, ask any specifying questions about design choices or anything else.