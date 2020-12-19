#pragma once

#include <Spacy/ScalarProduct.h>

namespace Spacy
{
    /// \f$ \|\cdot\|=\sqrt{(\cdot,\cdot)} \f$
    class HilbertSpaceNorm
    {
    public:
        explicit HilbertSpaceNorm( ScalarProduct sp );

        Real operator()( const Vector& x ) const;

    private:
        ScalarProduct sp_;
    };
}
