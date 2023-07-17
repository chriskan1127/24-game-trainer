#include <iostream>
#include <string>
#include <vector>
#include <cmath>
using namespace std;
class Solution{
private:
    vector<vector<string>> solutions;
    vector<string> first_solution;
    int max_generated;
public:
    vector<int> numbers;
    double target;
    Solution(vector<int> arg1){
        numbers = arg1;
        target = 24;
        max_generated = 1024;
    }
    Solution(vector<int> arg1, double arg2){
        numbers = arg1;
        target = arg2;
        max_generated = 1024;
    }
    Solution(vector<int> arg1, double arg2, int arg3){
        numbers = arg1;
        target = arg2;
        max_generated = arg3;
    }
    vector<vector<string>> get_all_solutions(){
        return solutions;
    }
    vector<string> get_first_solution(){
        return first_solution;
    }
    int get_max_generated(){
        return max_generated;
    }
    void set_max_generated(int arg1){
        max_generated = arg1;
    }
public:
    bool is_valid_input(){
        vector<double> values(numbers.begin(), numbers.end());
        return solution_exists(values, target);
    } 
    bool find_first_solution(){
        vector<double> values(numbers.begin(), numbers.end());
        vector<string> output;
        return solve_first(values, output, target);
    }
    void find_all_solutions(){
        solutions;
        vector<double> values(numbers.begin(), numbers.end());
        vector<string> output;
        solve_all(values, output, target);
        return;
    }
    void print_solutions(){
        for(int i = 0; i < solutions.size(); i++){
            cout << "Solution:" << endl;
            print_output_cpp(solutions[i]);
        }
    }
private: 
    void print_output_cpp(vector<string> output){
        for(int i = 0; i < output.size(); i++) 
            cout << output[i] << endl;
    }
private:
    bool solution_exists(vector<double>& nums, double target){
        if(nums.size() == 1){
            return fabs(nums[0] - target) < 1e-8;
        }
        double val;
        for(int i = 0; i + 1 < nums.size(); ++i){
            for(int j = i + 1; j < nums.size(); ++j){
                vector<double> new_nums;
                for(int k = 0; k < nums.size(); ++k)
                    if(k != i && k != j) new_nums.push_back(nums[k]);
                string val1 = to_string(nums[i]);
                string val2 = to_string(nums[j]); 
                //addition i, j
                val = nums[i] + nums[j];
                new_nums.push_back(val);
                if(solution_exists(new_nums, target)){
                    return true;
                }
                val = nums[i] * nums[j];
                new_nums.back() = val;
                if(solution_exists(new_nums, target)){
                    return true;
                }
                //subtraction i, j
                val = nums[i] - nums[j];
                new_nums.back() = val;
                if(solution_exists(new_nums, target)){
                    return true;
                }
                //division i, j
                val = nums[i] / nums[j];
                new_nums.back() = val;
                if(solution_exists(new_nums, target)){
                    return true;
                }
                //subtraction j, i
                val = nums[j] - nums[i];
                new_nums.back() = val;
                if(solution_exists(new_nums, target)){
                    return true;
                }
                //division j, i
                val = nums[j] / nums[i];
                new_nums.back() = val;
                if(solution_exists(new_nums, target)){
                    return true;
                }
            }
        }
        return false;
    }
    bool solve_first(vector<double>& nums, vector<string> prev_ops, double target){
        if(nums.size() == 1){
            if(fabs(nums[0] - target) < 1e-8){
                print_output_cpp(prev_ops);
                first_solution = prev_ops;
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
                if(solve_first(new_nums, output, target)){
                    return true;
                }
                output.pop_back();
                output.pop_back();
                val = nums[i] * nums[j];
                input = to_string(val);
                output.push_back(input);
                output.push_back("*");
                new_nums.back() = val;
                if(solve_first(new_nums, output, target)){
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
                if(solve_first(new_nums, output, target)){
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
                if(solve_first(new_nums, output, target)){
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
                if(solve_first(new_nums, output, target)){
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
                if(solve_first(new_nums, output, target)){
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
    void solve_all(vector<double>& nums, vector<string> prev_ops, double target){
        if(nums.size() == 1){
            if(fabs(nums[0] - target) < 1e-8){
                //print_output_cpp(prev_ops);
                solutions.push_back(prev_ops);
            }
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
                solve_all(new_nums, output, target);
                output.pop_back();
                output.pop_back();
                val = nums[i] * nums[j];
                input = to_string(val);
                output.push_back(input);
                output.push_back("*");
                new_nums.back() = val;
                solve_all(new_nums, output, target);
                //subtraction i, j
                output.pop_back();
                output.pop_back();
                val = nums[i] - nums[j];
                input = to_string(val);
                output.push_back(input);
                output.push_back("-");
                new_nums.back() = val;
                solve_all(new_nums, output, target);
                //division i, j
                output.pop_back();
                output.pop_back();
                val = nums[i] / nums[j];
                input = to_string(val);
                output.push_back(to_string(val));
                output.push_back("/");
                new_nums.back() = val;
                solve_all(new_nums, output, target);
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
                solve_all(new_nums, output, target);
                //division j, i
                output.pop_back();
                output.pop_back();
                val = nums[j] / nums[i];
                input = to_string(val);
                output.push_back(input);
                output.push_back("/");
                new_nums.back() = val;
                solve_all(new_nums, output, target);
                output.pop_back();
                output.pop_back();
                output.pop_back();
                output.pop_back();
            }
        }
        return;
    }

};


int main(){
    //get all solutions by running find_first_solution on all combinations
    vector<int> test{5, 5, 3, 2};
    double practice_target = 24;
    Solution stupid(test, practice_target);
    //int donkey = stupid.find_first_solution() ? 1: 0;
    //stupid.find_all_solutions();
    //stupid.print_solutions();
    bool lonkey = stupid.find_first_solution();
    int donkey = lonkey ? 1 : 0;
    cout << donkey << endl;
    return 1;
    /*
    + - *
    + - *
    */
}