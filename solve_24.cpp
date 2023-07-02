#include <iostream>
#include <string>
#include <vector>
#include <cmath>
using namespace std;
class Solution {
vector<string> solution;
public:
    bool judgePoint24(vector<int>& nums, double target) {
        vector<double> values(nums.begin(), nums.end());
        vector<string> output;
        return solve(values, output, target);
    }
private: 
    void print_output_cpp(vector<string> output){
        for(int i = 0; i < output.size(); i++) 
            cout << output[i] << endl;
    }
private:
    bool solve(vector<double>& nums, vector<string> prev_ops, double target){
        if(nums.size() == 1){
            if(fabs(nums[0] - target) < 1e-8){
                print_output_cpp(prev_ops);
                return true;
            }
            return false;
        }
        double val;
        string input;
        for(int i = 0; i + 1 < nums.size(); ++i){
            for(int j = i + 1; j < nums.size(); ++j){
                vector<string> output;
                output = prev_ops;
                vector<double> new_nums;
                for(int k = 0; k < nums.size(); ++k)
                    if(k != i && k != j) new_nums.push_back(nums[k]);
                string val1 = to_string(nums[i]);
                string val2 = to_string(nums[j]); 
                output.push_back(val1);
                output.push_back(val2);
                //addition i, j
                val = nums[i] + nums[j];
                input = to_string(val);
                output.push_back(input);
                output.push_back("+");
                new_nums.push_back(val);
                if(solve(new_nums, output, target)){
                    return true;
                }
                output.pop_back();
                output.pop_back();
                val = nums[i] * nums[j];
                input = to_string(val);
                output.push_back(input);
                output.push_back("*");
                new_nums.back() = val;
                if(solve(new_nums, output, target)){
                    return true;
                }
                //subtraction i, j
                output.pop_back();
                output.pop_back();
                val = nums[i] - nums[j];
                input = to_string(val);
                output.push_back(input);
                output.push_back("-");
                new_nums.back() = val;
                if(solve(new_nums, output, target)){
                    return true;
                }
                //division i, j
                output.pop_back();
                output.pop_back();
                val = nums[i] / nums[j];
                input = to_string(val);
                output.push_back(to_string(val));
                output.push_back("/");
                new_nums.back() = val;
                if(solve(new_nums, output, target)){
                    return true;
                }
                output.pop_back();
                output.pop_back();
                output.pop_back();
                output.pop_back();
                output.push_back(val2);
                output.push_back(val1);
                //subtraction j, i
                val = nums[j] - nums[i];
                input = to_string(val);
                output.push_back(input);
                output.push_back("-");
                new_nums.back() = val;
                if(solve(new_nums, output, target)){
                    return true;
                }
                //division j, i
                output.pop_back();
                output.pop_back();
                val = nums[j] / nums[i];
                input = to_string(val);
                output.push_back(input);
                output.push_back("/");
                new_nums.back() = val;
                if(solve(new_nums, output, target)){
                    return true;
                }
                output.pop_back();
                output.pop_back();
                output.pop_back();
                output.pop_back();
            }
        }
        return false;
    }
};
int main(){
    Solution s;
    vector<int> test{19, 34, 23, 1, 4, 5, 24};
    double practice_target = 24;
    int donkey = s.judgePoint24(test, practice_target) ? 1: 0;
    cout << donkey << endl;
    return donkey;
}