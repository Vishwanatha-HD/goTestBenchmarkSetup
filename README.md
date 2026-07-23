Point the $HOME env variable to the .git directory inside your home directory for all the git commands to work
Create a "scripts" directory and place all the 3 scripts in that directory

# The script "daily_go_benchmark_pipeline.sh" performs:
1. Checkout latest Go master branch
2. Build Go toolchain
3. Run ALL src micro-benchmarks (6 iterations)
4. Compare with previous day's results
5. Generate:
       - benchstat.txt
       - report.xlsx
       - report.html
6. Store metadata and logs
#

# The script "generate_dashboard.py" performs:
1. Parses benchstat txt file
2. Creates a HTML dashboard view, which looks as below:
3.   - Newly Introduced Improvements / Regressions
       (Captures the comparision window and Commit Range info)
         - Performance Improvements
         - Performance Regressions
4.   - Overall Package Benchmark Summary
         - Alarming Changes
         - Package Benchmark Results
#

# The script "generate_excel.py" performs:
1. Parses package blocks
2. Writes the complete information an excel file. The excel will have 2 tabs inside it
3.   - Format Summary Sheet
         - Contains all the package level geomean summary
4.   - Benchmark Details Sheet
         - Contains all the benchmarks info such as sec/op, alloc/op and b/op, for each of the package
