// The same using directives as decls.cs. A directive is an import; the
// `using var` statements in decls.cs are code and must stay countable.
using System;
using System.IO;
using System.Text;
using Alias = System.Collections.Generic.List<int>;

namespace Fixture
{
    public class Writer
    {
        public void Write(string path)
        {
            File.WriteAllText(path, Encoding.UTF8.WebName);
            Console.WriteLine(new Alias().Count);
        }
    }
}
